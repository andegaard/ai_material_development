"""
Agent X: Thermodynamic Simulator & Extrapolating Designer (v2)

Changes vs. v1:
- Reads Agent 1's baseline (manufacturing constraints) in addition to Agent 2's
  research report, and checks every extrapolated value against those
  constraints instead of extrapolating blind. v1 could (and in the bundled
  demo, silently did) produce a recipe that violates the company's own
  manufacturing limits.
- Handles every positively-correlated variable per finding, not just a single
  `optimizing_variable` string.
- Output is explicitly labeled `simulation_mode: "heuristic_linear_extrapolation"`
  instead of being presented as a validated thermodynamic simulation. A
  `run_calphad_simulation` hook marks where a real engine (Thermo-Calc
  TC-Python, or the open-source `pycalphad`) plugs in later.
- Defensive error handling: malformed/missing keys are logged and skipped
  rather than raising an uncaught KeyError mid-run.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="[Agent X] %(message)s")
logger = logging.getLogger("agent_x")

EXTRAPOLATION_FACTOR = 1.15  # +15% beyond literature max; see module docstring

# Maps legacy / ad-hoc baseline constraint keys (as produced by v1-style
# Agent 1 output, e.g. a flat "max_manganese_limit" field) to a chemical
# element symbol, so older baseline files still work. New Agent 1 output
# should use the `manufacturing_constraints` schema from
# agent_instructions.md v2 directly instead of relying on this table.
LEGACY_CONSTRAINT_KEY_MAP = {
    "max_manganese_limit": "Mn",
    "max_carbon_limit": "C",
    "max_silicon_limit": "Si",
    "max_chromium_limit": "Cr",
}


class AgentXSimulator:
  """Extrapolates candidate alloy recipes from Agent 2's research findings.

  IMPORTANT: `simulation_mode` in the output is always
  "heuristic_linear_extrapolation" unless `run_calphad_simulation` has been
  implemented and wired in below. This class does not perform real
  thermodynamic simulation on its own -- treat its "hypothesis" values as
  untested extrapolations, not validated predictions, until they have gone
  through an actual CALPHAD engine or physical lab testing.
  """

  def __init__(
      self,
      agent_2_report_path: str,
      agent_1_baseline_path: Optional[str] = None,
  ):
    self.extrapolated_plans: List[Dict[str, Any]] = []

    self.research_data = self._load_json(
        agent_2_report_path, required_keys=["breakthrough_findings"]
    )
    logger.info("Research trend report loaded from '%s'.", agent_2_report_path)

    self.baseline_constraints: Dict[str, Dict[str, Any]] = {}
    if agent_1_baseline_path:
      baseline = self._load_json(agent_1_baseline_path)
      self.baseline_constraints = self._extract_constraints(baseline)
      logger.info(
          "Loaded %d manufacturing constraint(s) from '%s'.",
          len(self.baseline_constraints), agent_1_baseline_path,
      )
    else:
      logger.warning(
          "No Agent 1 baseline provided -- extrapolated values will NOT be "
          "checked against real manufacturing constraints. Every "
          "constraint check below will report 'no_constraint_found'."
      )

  # ---------------------------------------------------------------- loading

  @staticmethod
  def _load_json(
      path: str, required_keys: Optional[List[str]] = None
  ) -> Dict[str, Any]:
    try:
      with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    except FileNotFoundError as exc:
      raise FileNotFoundError(
          f"Required input file not found: '{path}'. Check that the "
          "upstream agent ran and wrote its output here."
      ) from exc
    except json.JSONDecodeError as exc:
      raise ValueError(f"'{path}' is not valid JSON: {exc}") from exc

    if required_keys:
      missing = [k for k in required_keys if k not in data]
      if missing:
        raise ValueError(f"'{path}' is missing required key(s): {missing}")
    return data

  def _extract_constraints(
      self, baseline: Dict[str, Any]
  ) -> Dict[str, Dict[str, Any]]:
    """Supports both the new `manufacturing_constraints` schema (nested under
    each domain, per agent_instructions.md v2) and legacy flat keys like
    `max_manganese_limit`, so this still works against older Agent 1 output.
    """
    constraints: Dict[str, Dict[str, Any]] = {}

    # New schema: baseline["domains"][i]["manufacturing_constraints"]
    for domain in baseline.get("domains", []):
      for element, limit in domain.get("manufacturing_constraints", {}).items():
        if isinstance(limit, dict) and "max" in limit:
          constraints[element] = {
              "max": limit["max"],
              "unit": limit.get("unit", "wt%"),
          }

    # Legacy flat schema: baseline["max_manganese_limit"] etc.
    for key, element in LEGACY_CONSTRAINT_KEY_MAP.items():
      if key in baseline and element not in constraints:
        constraints[element] = {"max": baseline[key], "unit": "wt%"}

    return constraints

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
      composition_range = finding.get("chemical_composition_range") or {}

      # v1 only extrapolated the single `optimizing_variable`. A finding may
      # legitimately report several co-varying elements; extrapolate every
      # one that the finding actually names and has a `max` for.
      variables_to_extrapolate = self._variables_for_finding(
          finding, composition_range
      )

      if not variables_to_extrapolate:
        logger.warning(
            "Skipping finding '%s': no usable composition data for its "
            "optimizing_variable(s).", mechanism,
        )
        continue

      for variable in variables_to_extrapolate:
        range_for_variable = composition_range.get(variable)
        if not range_for_variable or "max" not in range_for_variable:
          logger.warning(
              "Skipping variable '%s' in finding '%s': no 'max' reported.",
              variable, mechanism,
          )
          continue

        tested_max = range_for_variable["max"]
        extrapolated_value = round(tested_max * EXTRAPOLATION_FACTOR, 3)
        constraint_check = self._check_constraint(variable, extrapolated_value)

        extrapolated_experiments.append({
            "target_mechanism": mechanism,
            "base_variable": variable,
            "literature_tested_max": tested_max,
            "extrapolated_target_value": extrapolated_value,
            "manufacturing_constraint_check": constraint_check,
            "hypothesis": (
                f"Extrapolating {variable} to {extrapolated_value} (above "
                f"literature max of {tested_max}) is hypothesized to "
                "increase the desired phase fraction. UNVALIDATED: derived "
                "from a linear extrapolation, not a thermodynamic "
                "simulation."
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
  def _variables_for_finding(
      finding: Dict[str, Any], composition_range: Dict[str, Any]
  ) -> List[str]:
    """`optimizing_variable` may be a single string (v1-style) or a list of
    strings (for findings that report several co-varying elements)."""
    raw = finding.get("optimizing_variable")
    if raw is None:
      return []
    variables = raw if isinstance(raw, list) else [raw]
    return [v for v in variables if v in composition_range]

  def _check_constraint(
      self, variable: str, extrapolated_value: float
  ) -> Dict[str, Any]:
    constraint = self.baseline_constraints.get(variable)
    if constraint is None:
      return {"limit": None, "unit": None, "status": "no_constraint_found"}

    status = (
        "exceeds_limit"
        if extrapolated_value > constraint["max"]
        else "within_limit"
    )
    return {
        "limit": constraint["max"],
        "unit": constraint.get("unit", "wt%"),
        "status": status,
    }

  # --------------------------------------------------------------- CALPHAD

  def run_calphad_simulation(self, *args, **kwargs):
    """Integration point for a real thermodynamic engine.

    Wire in Thermo-Calc's TC-Python API or the open-source `pycalphad`
    package here, and have `generate_simulation_output` call this instead of
    the placeholder phase-fraction/cooling-rate values below, once available.

    Left unimplemented on purpose: shipping fabricated phase-fraction
    numbers as if they came from a real simulation is worse than clearly
    labeling the current heuristic mode as unvalidated.
    """
    raise NotImplementedError(
        "No CALPHAD engine wired in yet. Keep simulation_mode set to "
        "'heuristic_linear_extrapolation' and do not report phase "
        "fractions as simulated results until this is implemented."
    )

  # ---------------------------------------------------------------- output

  def generate_simulation_output(self, output_path: str) -> Dict[str, Any]:
    """Generates the simulation results file consumed by Agent V / Agent 3."""
    any_exceeds_limit = any(
        p["manufacturing_constraint_check"]["status"] == "exceeds_limit"
        for p in self.extrapolated_plans
    )

    simulation_output = {
        "virtual_prototype": "Prototype_Extrapolated_X1",
        "simulation_mode": "heuristic_linear_extrapolation",
        "extrapolated_parameters": self.extrapolated_plans,
        # Placeholder values -- NOT derived from a real simulation. Do not
        # treat these as validated until run_calphad_simulation is
        # implemented and actually called above.
        "simulated_phase_fraction": {
            "retained_austenite": None,
            "bainite": None,
        },
        "required_cooling_rate_c_s": None,
        "confidence_note": (
            "Extrapolated via a flat +15% linear rule per variable, with no "
            "physics-based phase or cooling-rate modeling. Treat as a "
            "hypothesis list for lab validation, not a simulation result."
        ),
        "requires_human_review": any_exceeds_limit,
    }

    with open(output_path, "w", encoding="utf-8") as f:
      json.dump(simulation_output, f, indent=2)
    logger.info("Simulation results saved to '%s'.", output_path)

    if any_exceeds_limit:
      logger.warning(
          "One or more extrapolated parameters exceed Agent 1's "
          "manufacturing limits -- see 'manufacturing_constraint_check' in "
          "the output. Route to Agent V / human review before Agent 3."
      )
    return simulation_output


if __name__ == "__main__":
  # Demo reproducing the Mn scenario from the architecture review: Agent 1's
  # baseline caps Mn at 1.6 wt%, but the literature-extrapolated value
  # (1.8 * 1.15 = 2.07) exceeds it. v1 shipped this silently; v2 flags it.
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
      "breakthrough_findings": [{
          "mechanism": "Retained austenite stabilization via Si/Mn partitioning",
          "performance_correlation": "positive",
          "optimizing_variable": "Mn",
          "chemical_composition_range": {
              "C": {"min": 0.15, "max": 0.25},
              "Mn": {"min": 1.2, "max": 1.8},
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
        f"{p['base_variable']}: {p['extrapolated_target_value']} -> "
        f"{p['manufacturing_constraint_check']['status']}"
    )
