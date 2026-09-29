"""
Agent V: Independent Constraint Validator (v2, new in this revision)

Re-checks every `manufacturing_constraint_check` in Agent X's output
directly against Agent 1's baseline -- without trusting Agent X's own
verdict -- and flags any contradiction Agent X may have missed. Implemented
as pure code (per agent_instructions.md: "or pure code if the checks stay
simple") since the check itself is a deterministic comparison, and an
independent code path is a stronger check than another model call would be.

Reuses `common.extract_manufacturing_constraints`, the same function Agent X
uses, so "independent" means "re-derives the check from the same baseline",
not "re-implements a subtly different parser that could disagree by
accident". Scoped to the same domain as Agent X too: Agent X now writes the
domain it ran for into its own output, so Agent V reads that instead of
merging every domain's constraints together (which could otherwise silently
check an extrapolated value against the wrong domain's limit).

Agent X now extrapolates chemical composition, phase composition, and
heat-treatment variables (see agent_x_simulator.py). Agent 1's manufacturing
constraints are chemistry-only, so only `variable_category: "chemical"`
parameters get a real independent re-check against a wt% limit; phase and
heat-treatment parameters are only checked for being correctly labeled
`not_applicable` -- there is no constraint of that kind in Agent 1's data to
re-derive.
"""

import logging
from typing import Any, Dict, List, Optional

from common import extract_manufacturing_constraints, load_json_validated, save_json_validated

logging.basicConfig(level=logging.INFO, format="[Agent V] %(message)s")
logger = logging.getLogger("agent_v")


class AgentVValidator:
  def __init__(
      self,
      agent_1_baseline_path: str,
      agent_x_simulation_path: str,
      domain_name: Optional[str] = None,
  ):
    baseline = load_json_validated(agent_1_baseline_path, required_keys=["domains"])
    self.simulation = load_json_validated(
        agent_x_simulation_path, required_keys=["extrapolated_parameters"]
    )
    if domain_name is None:
      domain_name = self.simulation.get("domain")
    self.constraints = extract_manufacturing_constraints(baseline, domain_name=domain_name)

  def validate(self) -> List[Dict[str, Any]]:
    findings = []
    for param in self.simulation.get("extrapolated_parameters", []):
      variable = param.get("base_variable")
      category = param.get("variable_category", "chemical")  # default for pre-category simulation files
      value = param.get("extrapolated_target_value")
      claimed_status = (param.get("manufacturing_constraint_check") or {}).get("status")

      if category != "chemical":
        # Agent 1 has no manufacturing constraints for phase or
        # heat-treatment variables -- there's nothing of that kind to
        # independently re-derive. The only thing worth checking is that
        # Agent X labeled it "not_applicable" rather than claiming a wt%
        # constraint that doesn't exist for this kind of variable.
        recomputed_status = "not_applicable"
        disagreement = claimed_status != "not_applicable"
        needs_review = disagreement
      else:
        constraint = self.constraints.get(variable)
        if constraint is None or value is None:
          recomputed_status = "no_constraint_found"
        else:
          recomputed_status = "exceeds_limit" if value > constraint["max"] else "within_limit"

        # Per agent_instructions.md, Agent V halts the pipeline not just when
        # Agent X's own claim disagrees with the independent re-check, but
        # whenever the re-check itself finds `exceeds_limit` or
        # `no_constraint_found` -- even if Agent X already (correctly)
        # flagged the same thing. Only a recomputed `within_limit` that
        # matches Agent X's own claim is "confirmed" and needs no review.
        disagreement = recomputed_status != claimed_status
        needs_review = disagreement or recomputed_status != "within_limit"

      # "status" keeps the two-value enum from agent_instructions.md (it's
      # the halt/no-halt signal Agent 3 checks); for a phase/heat-treatment
      # variable "confirmed_within_limit" means "no issue found" rather than
      # literally "within a wt% limit" -- the precise picture is always in
      # recomputed_status.
      findings.append({
          "variable": variable,
          "variable_category": category,
          "extrapolated_target_value": value,
          "claimed_status": claimed_status,
          "recomputed_status": recomputed_status,
          "status": "contradiction_found" if needs_review else "confirmed_within_limit",
      })
      if disagreement:
        logger.warning(
            "Disagreement for '%s' (%s): Agent X claimed '%s', independent "
            "re-check found '%s'.",
            variable, category, claimed_status, recomputed_status,
        )
      elif needs_review:
        logger.warning(
            "'%s' independently confirmed as '%s' -- needs human review.",
            variable, recomputed_status,
        )
    return findings

  def generate_validation_output(self, output_path: str) -> Dict[str, Any]:
    findings = self.validate()
    any_contradiction = any(f["status"] == "contradiction_found" for f in findings)

    result = {"findings": findings, "requires_human_review": any_contradiction}
    save_json_validated(result, output_path, required_keys=["findings"])

    if any_contradiction:
      logger.warning(
          "Contradiction(s) found -- halt for human review before Agent 3 runs."
      )
    return result


if __name__ == "__main__":
  agent_v = AgentVValidator(
      agent_1_baseline_path="temp_data/agent_1_baseline.json",
      agent_x_simulation_path="temp_data/agent_x_simulation_results.json",
  )
  result = agent_v.generate_validation_output("temp_data/agent_v_validation.json")

  print("\n--- Independent validation result ---")
  for f in result["findings"]:
    print(f"[{f['variable_category']}] {f['variable']}: {f['recomputed_status']} -> {f['status']}")
