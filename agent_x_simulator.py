"""
Agent X: Thermodynamic Simulator & Extrapolating Designer (v2)

IMPORTANT -- what this actually does today: there is no real thermodynamics
here. `simulation_mode` in the output reflects whichever `SimulationEngine`
is in use, and the only one implemented (`HeuristicLinearEngine`) does one
thing: take a positively-correlated variable's literature-tested max and
push it 15% further (`EXTRAPOLATION_FACTOR`). No Gibbs-energy minimization,
no phase diagram, no CCT/TTT kinetics. Treat every "hypothesis" below as an
untested extrapolation, not a validated prediction, until it has gone
through an actual CALPHAD engine or physical lab testing.

Engine seam, so swapping in real thermodynamics later doesn't require
restructuring the pipeline: `SimulationEngine` is the interface; pass a
different implementation via `AgentXSimulator(..., engine=SomeEngine())` and
everything else -- constraint checking, output shape, Agent V's independent
check -- keeps working unchanged. `CalphadEngine` below is the documented,
unimplemented stub for when a Thermo-Calc TC-Python license or a pycalphad
+ thermodynamic-database setup becomes available.

Handles four kinds of extrapolation target per finding, not just chemistry:
chemical composition, phase composition, heat-treatment parameters, and
mechanical properties themselves when that's what the literature reports a
range for (see agent_2_frontier_research.py's finding schema). Agent 1's
manufacturing constraints are chemistry-only, so only chemical-category
variables get a real `within_limit`/`exceeds_limit` check; everything else
is reported with status `not_applicable` since there is no constraint of
that kind to check against -- this is a real "nothing to check", not the
same thing as `no_constraint_found` (a chemical element Agent 1 simply
didn't report a limit for).

A finding's `reported_mechanical_properties` (a single value reported at the
literature-tested condition, not a range) is never extrapolated -- there's
no physics model here connecting composition to mechanical outcome -- but it
is carried through onto every extrapolated_parameters entry from that
finding as `literature_reported_properties`, so the actual measured context
behind a hypothesis stays visible instead of being silently dropped.

Reads Agent 1's baseline (manufacturing constraints) in addition to Agent
2's research report, and checks every chemical extrapolation against those
constraints instead of extrapolating blind -- scoped to the one domain
Agent 2 was scoped to (see common.extract_manufacturing_constraints).
Malformed/missing keys are logged and skipped rather than raising an
uncaught KeyError mid-run.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from common import extract_manufacturing_constraints, load_json_validated, save_json_validated

logging.basicConfig(level=logging.INFO, format="[Agent X] %(message)s")
logger = logging.getLogger("agent_x")

EXTRAPOLATION_FACTOR = 1.15  # +15% beyond literature max; see module docstring

# Where to look for a named `optimizing_variable` on a finding, in order,
# and what category to tag it with once found.
RANGE_FIELDS = [
    ("chemical_composition_range", "chemical"),
    ("phase_composition_range", "phase"),
    ("heat_treatment_range", "heat_treatment"),
    ("mechanical_property_range", "mechanical_property"),
]


class SimulationEngine:
  """Interface an Agent X extrapolation backend must implement.

  `HeuristicLinearEngine` below is the only implementation today. A future
  real engine (`CalphadEngine`, or a Thermo-Calc TC-Python-backed one)
  implements the same interface and is swapped in via
  `AgentXSimulator(engine=...)` -- nothing else in the pipeline changes.
  """

  MODE_LABEL = "unknown"

  def extrapolate(
      self, finding: Dict[str, Any], variable: str, category: str, literature_range: Dict[str, Any]
  ) -> Optional[Dict[str, Any]]:
    """Given one (variable, category, literature_range) drawn from a single
    positively-correlated finding, return
    {"literature_tested_max": ..., "extrapolated_target_value": ...}, or
    None if this engine can't extrapolate this input (logged and skipped by
    the caller, never raised)."""
    raise NotImplementedError


class HeuristicLinearEngine(SimulationEngine):
  """+15% linear extrapolation beyond the literature-tested max, per
  variable. Not a validated thermodynamic simulation -- see module
  docstring. Phase fractions are additionally clamped at 100%, since unlike
  a chemical composition or a temperature, a phase fraction has a hard
  physical ceiling that a flat percentage bump can otherwise exceed.
  """

  MODE_LABEL = "heuristic_linear_extrapolation"

  def extrapolate(self, finding, variable, category, literature_range):
    tested_max = literature_range.get("max")
    if tested_max is None:
      return None

    try:
      extrapolated_value = round(tested_max * EXTRAPOLATION_FACTOR, 3)
    except TypeError:
      # The model returned a non-numeric "max" (e.g. a string) -- there's no
      # key presence check that catches a wrong value *type*, so this
      # degrades to "can't extrapolate" (logged and skipped by the caller)
      # instead of crashing the whole run on one malformed finding.
      logger.warning(
          "Variable '%s' has a non-numeric literature max (%r); cannot extrapolate.",
          variable, tested_max,
      )
      return None

    if category == "phase":
      extrapolated_value = min(extrapolated_value, 100.0)

    return {"literature_tested_max": tested_max, "extrapolated_target_value": extrapolated_value}


class CalphadEngine(SimulationEngine):
  """Placeholder for a real thermodynamic engine -- Thermo-Calc TC-Python
  (commercial, needs an existing license) or `pycalphad` (open source, but
  needs a thermodynamic database (TDB) for the relevant alloy system, which
  is not included here and may need to be sourced or built).

  To wire this in: implement `extrapolate` to run an actual equilibrium (or
  kinetic) calculation for the given composition/phase/heat-treatment
  variable instead of linear extrapolation, and pass
  `AgentXSimulator(..., engine=CalphadEngine(...))`. Everything else --
  constraint checking against Agent 1's baseline, Agent V's independent
  check, Agent 3's roadmap generation -- keeps working unchanged, since they
  all consume this engine's output shape, not its internals.

  Left unimplemented on purpose: shipping fabricated phase-fraction numbers
  as if they came from a real simulation is worse than clearly labeling the
  current heuristic mode as unvalidated.
  """

  MODE_LABEL = "calphad"

  def extrapolate(self, finding, variable, category, literature_range):
    raise NotImplementedError(
        "No CALPHAD engine wired in yet. Implement this against pycalphad "
        "or Thermo-Calc TC-Python, then pass "
        "AgentXSimulator(engine=CalphadEngine(...)) to use it."
    )


class AgentXSimulator:
  """Extrapolates candidate alloy recipes from Agent 2's research findings,
  using whichever `SimulationEngine` is configured (default: the heuristic
  linear one). See module docstring for what "simulation" does and doesn't
  mean here.
  """

  def __init__(
      self,
      agent_2_report_path: str,
      agent_1_baseline_path: Optional[str] = None,
      domain_name: Optional[str] = None,
      engine: Optional[SimulationEngine] = None,
  ):
    self.engine = engine or HeuristicLinearEngine()
    self.extrapolated_plans: List[Dict[str, Any]] = []

    self.research_data = load_json_validated(
        agent_2_report_path, required_keys=["breakthrough_findings"]
    )
    logger.info("Research trend report loaded from '%s'.", agent_2_report_path)

    # Agent 2's report is scoped to one domain (`self.research_data["domain"]`).
    # Default to that domain's own constraints rather than merging every
    # domain in the baseline together, unless the caller overrides it. This
    # resolved name is also written into our own output file below, so
    # Agent V can pick up the same domain automatically.
    if domain_name is None:
      domain_name = self.research_data.get("domain")
    self.domain_name = domain_name

    self.baseline_constraints: Dict[str, Dict[str, Any]] = {}
    if agent_1_baseline_path:
      baseline = load_json_validated(agent_1_baseline_path)
      self.baseline_constraints = extract_manufacturing_constraints(baseline, domain_name=domain_name)
      logger.info(
          "Loaded %d manufacturing constraint(s) for domain '%s' from '%s'.",
          len(self.baseline_constraints), domain_name, agent_1_baseline_path,
      )
    else:
      logger.warning(
          "No Agent 1 baseline provided -- extrapolated chemical values will "
          "NOT be checked against real manufacturing constraints. Every "
          "constraint check below will report 'no_constraint_found'."
      )

  # ------------------------------------------------------------ extrapolate

  def isolate_and_extrapolate_positive_trends(self) -> List[Dict[str, Any]]:
    logger.info(
        "Analyzing trends and isolating positive performance correlations..."
    )
    extrapolated_experiments = []

    for finding in self.research_data.get("breakthrough_findings", []):
      if finding.get("performance_correlation") != "positive":
        continue

      mechanism = finding.get("mechanism", "unknown mechanism")
      resolved_variables = self._variables_for_finding(finding)

      if not resolved_variables:
        logger.warning(
            "Skipping finding '%s': no usable variable data across "
            "chemical/phase/heat-treatment/mechanical-property ranges.", mechanism,
        )
        continue

      for resolved in resolved_variables:
        variable, category, range_for_variable = (
            resolved["variable"], resolved["category"], resolved["range"],
        )

        if "max" not in range_for_variable:
          logger.warning(
              "Skipping %s variable '%s' in finding '%s': no 'max' reported.",
              category, variable, mechanism,
          )
          continue

        extrapolation = self.engine.extrapolate(finding, variable, category, range_for_variable)
        if extrapolation is None:
          logger.warning(
              "Engine could not extrapolate %s variable '%s' in finding '%s'.",
              category, variable, mechanism,
          )
          continue

        extrapolated_value = extrapolation["extrapolated_target_value"]
        tested_max = extrapolation["literature_tested_max"]

        # Agent 1's manufacturing constraints are chemistry-only (element wt%
        # limits) -- phase and heat-treatment variables have no such ceiling
        # to check against at all, which is a real "not applicable", not the
        # same thing as a chemical element Agent 1 simply didn't report a
        # limit for ("no_constraint_found").
        if category == "chemical":
          constraint_check = self._check_constraint(variable, extrapolated_value)
        else:
          constraint_check = {"limit": None, "unit": None, "status": "not_applicable"}

        extrapolated_experiments.append({
            "target_mechanism": mechanism,
            "base_variable": variable,
            "variable_category": category,
            "literature_tested_max": tested_max,
            "extrapolated_target_value": extrapolated_value,
            "manufacturing_constraint_check": constraint_check,
            # Grounding context, not extrapolated -- see module docstring.
            "literature_reported_properties": finding.get("reported_mechanical_properties") or {},
            "hypothesis": (
                f"Extrapolating {category} variable '{variable}' to "
                f"{extrapolated_value} (above literature max of {tested_max}) "
                "is hypothesized to improve the domain's performance "
                f"priorities. UNVALIDATED: derived from {self.engine.MODE_LABEL}, "
                "not a thermodynamic simulation."
            ),
        })

        if constraint_check["status"] == "exceeds_limit":
          logger.warning(
              "Extrapolated %s = %s exceeds the manufacturing limit (%s "
              "%s) from Agent 1's baseline. Flagging for review.",
              variable, extrapolated_value,
              constraint_check["limit"], constraint_check["unit"],
          )

    self.extrapolated_plans = extrapolated_experiments
    return extrapolated_experiments

  @staticmethod
  def _variables_for_finding(finding: Dict[str, Any]) -> List[Dict[str, Any]]:
    """`optimizing_variable` may be a single string or a list of strings.
    Resolve each name against whichever of the finding's range fields
    (chemical/phase/heat-treatment) actually defines it, so Agent X isn't
    limited to chemistry."""
    raw = finding.get("optimizing_variable")
    if raw is None:
      return []
    names = raw if isinstance(raw, list) else [raw]

    resolved = []
    for name in names:
      for field, category in RANGE_FIELDS:
        range_dict = finding.get(field) or {}
        if name in range_dict:
          resolved.append({"variable": name, "category": category, "range": range_dict[name]})
          break
      else:
        logger.warning(
            "Skipping variable '%s' in finding '%s': not found in any range "
            "field (chemical/phase/heat_treatment/mechanical_property).",
            name, finding.get("mechanism", "unknown mechanism"),
        )
    return resolved

  def _check_constraint(
      self, variable: str, extrapolated_value: float
  ) -> Dict[str, Any]:
    constraint = self.baseline_constraints.get(variable)
    if constraint is None:
      return {"limit": None, "unit": None, "status": "no_constraint_found"}

    try:
      status = "exceeds_limit" if extrapolated_value > constraint["max"] else "within_limit"
    except TypeError:
      # constraint["max"] is present but not a number (e.g. Agent 1's model
      # output a string) -- there's genuinely no usable limit to check
      # against, which is exactly what "no_constraint_found" already means.
      logger.warning(
          "Manufacturing constraint for '%s' has a non-numeric max (%r); "
          "treating as no usable constraint.",
          variable, constraint.get("max"),
      )
      return {"limit": None, "unit": None, "status": "no_constraint_found"}

    return {
        "limit": constraint["max"],
        "unit": constraint.get("unit", "wt%"),
        "status": status,
    }

  # ---------------------------------------------------------------- output

  def generate_simulation_output(self, output_path: str) -> Dict[str, Any]:
    """Generates the simulation results file consumed by Agent V / Agent 3."""
    any_exceeds_limit = any(
        p["manufacturing_constraint_check"]["status"] == "exceeds_limit"
        for p in self.extrapolated_plans
    )

    simulation_output = {
        "virtual_prototype": "Prototype_Extrapolated_X1",
        "domain": self.domain_name,
        "simulation_mode": self.engine.MODE_LABEL,
        "extrapolated_parameters": self.extrapolated_plans,
        # Placeholder values -- NOT derived from a real simulation. Stay None
        # until a real engine (see CalphadEngine) actually computes them.
        "simulated_phase_fraction": {
            "retained_austenite": None,
            "bainite": None,
        },
        "required_cooling_rate_c_s": None,
        "confidence_note": (
            f"Extrapolated via {self.engine.MODE_LABEL} "
            f"({EXTRAPOLATION_FACTOR}x factor per variable, across chemical "
            "composition, phase composition, heat-treatment, and mechanical-"
            "property findings), with no physics-based phase or "
            "cooling-rate modeling. Treat as a hypothesis list for lab "
            "validation, not a simulation result."
        ),
        "requires_human_review": any_exceeds_limit,
    }

    save_json_validated(
        simulation_output,
        output_path,
        required_keys=["virtual_prototype", "simulation_mode", "extrapolated_parameters"],
    )

    if any_exceeds_limit:
      logger.warning(
          "One or more extrapolated parameters exceed Agent 1's "
          "manufacturing limits -- see 'manufacturing_constraint_check' in "
          "the output. Route to Agent V / human review before Agent 3."
      )
    return simulation_output


if __name__ == "__main__":
  # Demo covering all four variable categories: a chemical element that
  # exceeds Agent 1's Mn ceiling (the original architecture-review scenario:
  # 1.8 * 1.15 = 2.07 > 1.6), a phase fraction and a heat-treatment
  # parameter (no manufacturing constraint of that kind exists for either,
  # so both are "not_applicable"), and a mechanical property reported as a
  # range (hardness varied across trials) -- plus a *separate*
  # reported_mechanical_properties single data point, to show it's carried
  # through as context rather than extrapolated.
  os.makedirs("temp_data", exist_ok=True)

  mock_agent_1_baseline = {
      "company": "Company A",
      "domains": [{
          "domain_name": "Wear-Resistant",
          "grades": ["Wear-Resistant 400"],
          "manufacturing_constraints": {
              "Mn": {"max": 1.6, "unit": "wt%"},
          },
      }],
  }
  with open("temp_data/agent_1_baseline.json", "w", encoding="utf-8") as f:
    json.dump(mock_agent_1_baseline, f, indent=2)

  mock_agent_2_report = {
      "domain": "Wear-Resistant",
      "breakthrough_findings": [{
          "mechanism": "Retained austenite stabilization via Si/Mn partitioning",
          "performance_correlation": "positive",
          "optimizing_variable": ["Mn", "retained_austenite", "tempering_temp_c", "hardness_hbw"],
          "chemical_composition_range": {
              "C": {"min": 0.15, "max": 0.25},
              "Mn": {"min": 1.2, "max": 1.8},
          },
          "phase_composition_range": {
              "retained_austenite": {"min": 8, "max": 92},
          },
          "heat_treatment_range": {
              "tempering_temp_c": {"min": 150, "max": 250, "unit": "C"},
          },
          "mechanical_property_range": {
              "hardness_hbw": {"min": 380, "max": 420, "unit": "HBW"},
          },
          "reported_mechanical_properties": {
              "impact_toughness_j": {"value": 45, "unit": "J"},
          },
      }]
  }
  with open("temp_data/agent_2_report.json", "w", encoding="utf-8") as f:
    json.dump(mock_agent_2_report, f, indent=2)

  agent_x = AgentXSimulator(
      agent_2_report_path="temp_data/agent_2_report.json",
      agent_1_baseline_path="temp_data/agent_1_baseline.json",
  )
  agent_x.isolate_and_extrapolate_positive_trends()
  result = agent_x.generate_simulation_output(
      "temp_data/agent_x_simulation_results.json"
  )

  print("\n--- Constraint check result ---")
  for p in result["extrapolated_parameters"]:
    print(
        f"[{p['variable_category']}] {p['base_variable']}: "
        f"{p['extrapolated_target_value']} -> "
        f"{p['manufacturing_constraint_check']['status']} "
        f"(literature context: {p['literature_reported_properties']})"
    )
