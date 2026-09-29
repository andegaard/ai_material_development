import json
import os


class AgentXSimulator:

  def __init__(self, agent_2_report_path: str):
    self.load_report(agent_2_report_path)

  def load_report(self, path: str):
    with open(path, "r", encoding="utf-8") as f:
      self.research_data = json.load(f)
    print("[Agent X] Research trend report successfully loaded.")

  def isolate_and_extrapolate_positive_trends(self):
    print(
        "[Agent X] Analyzing trends and isolating positive performance"
        " correlations..."
    )
    extrapolated_experiments = []

    for finding in self.research_data.get("breakthrough_findings", []):
      if finding.get("performance_correlation") == "positive":
        baseline_alloy = finding.get("chemical_composition_range")
        trend_vector = finding.get("optimizing_variable")
        tested_max = baseline_alloy[trend_vector]["max"]

        # Extrapolate beyond literature limits (+15%)
        extrapolated_value = round(tested_max * 1.15, 3)

        extrapolated_experiment = {
            "target_mechanism": finding.get("mechanism"),
            "base_variable": trend_vector,
            "literature_tested_max": tested_max,
            "extrapolated_target_value": extrapolated_value,
            "hypothesis": (
                f"Extrapolating {trend_vector} to {extrapolated_value}% (above"
                f" literature max of {tested_max}%) is expected to increase"
                " desired phase fraction."
            ),
        }
        extrapolated_experiments.append(extrapolated_experiment)

    self.extrapolated_plans = extrapolated_experiments
    return extrapolated_experiments

  def generate_simulation_output(self, output_path: str):
    """Generates simulation results file to be consumed by Agent 3."""
    simulation_output = {
        "virtual_prototype": "Prototype_Extrapolated_X1",
        "extrapolated_parameters": self.extrapolated_plans,
        "simulated_phase_fraction": {
            "retained_austenite": 0.15,
            "bainite": 0.85,
        },
        "required_cooling_rate_c_s": 35,
    }

    with open(output_path, "w", encoding="utf-8") as f:
      json.dump(simulation_output, f, indent=2)
    print(f"[Agent X] Simulation results saved to '{output_path}'.")


if __name__ == "__main__":
  # Example execution with mock data
  os.makedirs("temp_data", exist_ok=True)
  mock_report = {
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
  with open("temp_data/agent_2_report.json", "w") as f:
    json.dump(mock_report, f)

  agent_x = AgentXSimulator("temp_data/agent_2_report.json")
  agent_x.isolate_and_extrapolate_positive_trends()
  agent_x.generate_simulation_output("temp_data/agent_x_simulation_results.json")