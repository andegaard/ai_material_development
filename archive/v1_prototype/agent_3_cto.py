import json
import os
from anthropic import Anthropic


class Agent3CTO:

  def __init__(self, api_key: str = None):
    self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    self.model = "claude-3-opus-20240229"

  def load_inputs(self, baseline_path: str, simulation_path: str):
    with open(baseline_path, "r", encoding="utf-8") as f:
      self.baseline_data = json.load(f)
    with open(simulation_path, "r", encoding="utf-8") as f:
      self.simulation_data = json.load(f)
    print("[Agent 3] Successfully loaded baseline and simulation results.")

  def perform_gap_analysis_and_triz(self) -> str:
    system_prompt = (
        "You are the Chief Technology Officer (CTO) and expert industrial metallurgist "
        "specializing in TRIZ (Theory of Inventive Problem Solving) and R&D strategy.\n"
        "Your task is to bridge the gap between the company's current manufacturing capabilities "
        "(Agent 1) and simulated advanced virtual alloy recipes (Agent X).\n"
        "Identify technical trade-offs, resolve them using TRIZ inventive principles, "
        "and deliver a concrete R&D implementation roadmap."
    )

    user_message = f"""
    Here is the data for your analysis:

    1. COMPANY A BASELINE PORTFOLIO (Agent 1):
    {json.dumps(self.baseline_data, indent=2)}

    2. SIMULATED EXTRAPOLATED ALLOY RECIPES (Agent X):
    {json.dumps(self.simulation_data, indent=2)}

    Please generate a comprehensive Strategic Gap Analysis & R&D Roadmap covering:
    1. Performance/process gaps between current production and simulated prototypes.
    2. Technical contradictions encountered (e.g., strength vs weldability).
    3. Specific TRIZ principles applied to bypass these limitations.
    4. A 3-step actionable development roadmap for Company A.
    """

    print("[Agent 3] Running gap analysis and applying TRIZ via Claude Opus...")
    response = self.client.messages.create(
        model=self.model,
        temperature=0.4,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text

  def save_report(self, report: str, output_path: str = "agent_3_roadmap.md"):
    with open(output_path, "w", encoding="utf-8") as f:
      f.write(report)
    print(f"[Agent 3] R&D Roadmap saved to '{output_path}'.")


if __name__ == "__main__":
  os.makedirs("temp_data", exist_ok=True)
  # Mock input files for testing
  with open("temp_data/agent_1_baseline.json", "w") as f:
    json.dump(
        {
            "company": "Company A",
            "primary_grades": ["Wear-Resistant 400"],
            "max_manganese_limit": 1.6,
        },
        f,
    )

  agent_3 = Agent3CTO()
  agent_3.load_inputs(
      "temp_data/agent_1_baseline.json",
      "temp_data/agent_x_simulation_results.json",
  )
  roadmap = agent_3.perform_gap_analysis_and_triz()
  agent_3.save_report(roadmap, "temp_data/agent_3_roadmap.md")