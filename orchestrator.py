"""
Pipeline Orchestrator (v2)

Runs the full multi-agent steel R&D pipeline described in
agent_instructions.md end to end, including the two human-in-the-loop
checkpoints and the halt-on-contradiction behavior after Agent V:

Agent 1 -> [Checkpoint 1: pick domain] -> Agent 2 -> Agent X -> Agent V ->
[halt + review if contradiction_found] -> Agent 3 ->
[Checkpoint 2: approve roadmap] -> Agent 4 -> consolidated PDF report

Usage:
    python orchestrator.py "Company Name" "https://company-website.com"

All output files for a run are written under runs/<sanitized company name>/,
so each company's project data stays in its own folder. Re-running the same
company name reuses (and overwrites) that same folder rather than creating a
new one each time.

A consolidated PDF report (see report_builder.py) is built at the end of a
full run, and also on any halt -- whatever stages completed are rendered
normally, anything that didn't run yet is labeled as such.
"""

import argparse
import logging
import os
import re

from agent_1_market_intelligence import Agent1MarketIntelligence
from agent_2_frontier_research import Agent2FrontierResearch
from agent_3_gap_analysis import Agent3GapAnalysis
from agent_4_ip_lca_audit import Agent4IPAndLCAAudit
from agent_v_validator import AgentVValidator
from agent_x_simulator import AgentXSimulator
from common import PipelineHalt
from report_builder import build_report

logging.basicConfig(level=logging.INFO, format="[Orchestrator] %(message)s")
logger = logging.getLogger("orchestrator")

RUNS_DIR = "runs"


def _sanitize_folder_name(name: str) -> str:
  """Turn a company name into a safe, filesystem-friendly directory name."""
  sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
  return sanitized.strip("_") or "unnamed_company"


def run_pipeline(company: str, company_url: str, data_dir: str) -> None:
  os.makedirs(data_dir, exist_ok=True)

  def _path(name: str) -> str:
    return os.path.join(data_dir, name)

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
    selected_domain = domains[int(choice) - 1]
  except (ValueError, IndexError):
    raise PipelineHalt(f"Invalid domain selection: {choice!r}")
  logger.info("Human selected domain: '%s'", selected_domain.get("domain_name"))

  logger.info("=== STEP 2: Agent 2 (Frontier Research) ===")
  agent_2 = Agent2FrontierResearch()
  agent_2_result = agent_2.run(selected_domain, output_path=_path("agent_2_report.json"))

  print("\n--- Performance priorities identified for this domain ---")
  for p in agent_2_result.get("performance_priorities", []):
    print(f"- {p.get('property')} ({p.get('direction')}): {p.get('rationale')}")

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
      agent_2_report_path=_path("agent_2_report.json"),
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

  report_path = build_report(data_dir=data_dir, output_path=_path("pipeline_report.pdf"))
  logger.info("=== PIPELINE COMPLETE. See '%s/' for all reports, including '%s'. ===", data_dir, report_path)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Run the multi-agent steel R&D pipeline for one company."
  )
  parser.add_argument("company", help="Company name, e.g. 'SSAB'")
  parser.add_argument("company_url", help="Company's main web page, e.g. 'https://www.ssab.com'")
  args = parser.parse_args()

  data_dir = os.path.join(RUNS_DIR, _sanitize_folder_name(args.company))

  try:
    run_pipeline(company=args.company, company_url=args.company_url, data_dir=data_dir)
  except PipelineHalt as exc:
    logger.error("Pipeline halted: %s", exc)
    # Still worth a report -- whatever stages did complete are rendered
    # normally, and anything that didn't run yet is labeled as such rather
    # than silently missing.
    build_report(data_dir=data_dir, output_path=os.path.join(data_dir, "pipeline_report.pdf"))
    raise SystemExit(1)
