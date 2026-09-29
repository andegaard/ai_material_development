"""
Pipeline Orchestrator (v2)

Runs the full multi-agent steel R&D pipeline described in
agent_instructions.md end to end, including the two human-in-the-loop
checkpoints and the halt-on-contradiction behavior after Agent V:

Agent 1 -> [Checkpoint 1: pick domain] -> Agent 2 -> Agent X -> Agent V ->
[halt + review if contradiction_found] -> Agent 3 ->
[Checkpoint 2: approve roadmap] -> Agent 4
"""

import logging
import os

from agent_1_market_intelligence import Agent1MarketIntelligence
from agent_2_frontier_research import Agent2FrontierResearch
from agent_3_gap_analysis import Agent3GapAnalysis
from agent_4_ip_lca_audit import Agent4IPAndLCAAudit
from agent_v_validator import AgentVValidator
from agent_x_simulator import AgentXSimulator
from common import PipelineHalt

logging.basicConfig(level=logging.INFO, format="[Orchestrator] %(message)s")
logger = logging.getLogger("orchestrator")

DATA_DIR = "temp_data"


def _path(name: str) -> str:
  return os.path.join(DATA_DIR, name)


def run_pipeline(company: str, company_url: str) -> None:
  os.makedirs(DATA_DIR, exist_ok=True)

  logger.info("=== STEP 1: Agent 1 (Market Intelligence) ===")
  agent_1 = Agent1MarketIntelligence()
  baseline = agent_1.run(company, company_url, output_path=_path("agent_1_baseline.json"))

  domains = baseline.get("domains", [])
  if not domains:
    raise PipelineHalt("Agent 1 found no domains to select from.")

  print("\n--- Domains found ---")
  for i, domain in enumerate(domains, start=1):
    print(f"{i}. {domain.get('domain_name')} ({len(domain.get('grades', []))} grades)")

  print("\n\U0001F6D1 Human-in-the-Loop Checkpoint 1: Domain Selection")
  choice = input(f"Select a domain [1-{len(domains)}] to drive Agent 2: ").strip()
  try:
    selected_domain = domains[int(choice) - 1]["domain_name"]
  except (ValueError, IndexError):
    raise PipelineHalt(f"Invalid domain selection: {choice!r}")
  logger.info("Human selected domain: '%s'", selected_domain)

  logger.info("=== STEP 2: Agent 2 (Frontier Research) ===")
  agent_2 = Agent2FrontierResearch()
  agent_2.run(selected_domain, output_path=_path("agent_2_report.json"))

  logger.info("=== STEP X: Agent X (Simulation & Extrapolation) ===")
  agent_x = AgentXSimulator(
      agent_2_report_path=_path("agent_2_report.json"),
      agent_1_baseline_path=_path("agent_1_baseline.json"),
  )
  agent_x.isolate_and_extrapolate_positive_trends()
  agent_x.generate_simulation_output(_path("agent_x_simulation_results.json"))

  logger.info("=== STEP V: Agent V (Independent Validation) ===")
  agent_v = AgentVValidator(
      agent_1_baseline_path=_path("agent_1_baseline.json"),
      agent_x_simulation_path=_path("agent_x_simulation_results.json"),
  )
  validation = agent_v.generate_validation_output(_path("agent_v_validation.json"))

  if validation["requires_human_review"]:
    print("\n\U0001F6D1 Agent V found issue(s) requiring review before Agent 3 runs:")
    for finding in validation["findings"]:
      if finding["status"] == "contradiction_found":
        print(f"  - {finding}")
    proceed = input("Proceed to Agent 3 anyway? [y/N]: ").strip().lower()
    if proceed != "y":
      raise PipelineHalt("Halted at Agent V checkpoint by human operator.")

  logger.info("=== STEP 3: Agent 3 (Gap Analysis & TRIZ) ===")
  agent_3 = Agent3GapAnalysis()
  agent_3.run(
      agent_1_baseline_path=_path("agent_1_baseline.json"),
      agent_x_simulation_path=_path("agent_x_simulation_results.json"),
      agent_v_validation_path=_path("agent_v_validation.json"),
      markdown_output_path=_path("agent_3_roadmap.md"),
      json_output_path=_path("agent_3_roadmap.json"),
  )

  print("\n\U0001F6D1 Human-in-the-Loop Checkpoint 2: Roadmap Review")
  print(f"Review '{_path('agent_3_roadmap.md')}' before continuing to Agent 4.")
  proceed = input("Approve roadmap and proceed to Agent 4 (IP/LCA audit)? [y/N]: ").strip().lower()
  if proceed != "y":
    raise PipelineHalt("Halted at roadmap review checkpoint by human operator.")

  logger.info("=== STEP 4: Agent 4 (IP-Freedom & LCA Audit) ===")
  agent_4 = Agent4IPAndLCAAudit()
  agent_4.run(
      agent_3_roadmap_json_path=_path("agent_3_roadmap.json"),
      markdown_output_path=_path("agent_4_audit.md"),
      json_output_path=_path("agent_4_audit.json"),
  )

  logger.info("=== PIPELINE COMPLETE. See '%s/' for all reports. ===", DATA_DIR)


if __name__ == "__main__":
  try:
    run_pipeline(company="SSAB", company_url="https://www.ssab.com")
  except PipelineHalt as exc:
    logger.error("Pipeline halted: %s", exc)
    raise SystemExit(1)
