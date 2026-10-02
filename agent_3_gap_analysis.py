"""
Agent 3: Strategic Gap Analysis & TRIZ Problem Solver (v2)

Compares current manufacturing capabilities (Agent 1) against Agent X's
extrapolated recipes, resolving technical trade-offs via TRIZ / first
principles. Takes Agent V's validation findings as an explicit input: any
`contradiction_found` entry must be addressed in the roadmap rather than
silently built upon, per agent_instructions.md section 4.

Also takes Agent 2's full report directly, not just what Agent X extracted
from it. Agent X only carries forward findings it could resolve as a named
variable against one of its four range fields -- Agent 2's
`materials_found` (complete comparator alloys from the literature) and any
finding Agent X's narrow per-variable logic didn't pick up would otherwise
never reach this stage at all. Agent 3 is the one agent positioned to
actually compare the company's current materials against what the broader
literature describes, so it needs the full picture, not a pre-filtered
slice of it.

Produces both deliverables the spec calls for -- a human-readable Markdown
narrative and a structured JSON form for Agent 4 -- from a single model
call, so the two can't drift apart from each other.
"""

import json
import logging
from typing import Any, Dict

from common import (
    call_with_retry,
    extract_json_object,
    extract_text,
    get_anthropic_client,
    load_json_validated,
    require_keys,
    save_json_validated,
)

logging.basicConfig(level=logging.INFO, format="[Agent 3] %(message)s")
logger = logging.getLogger("agent_3")

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are the Chief Technology Officer and an expert
industrial metallurgist specializing in TRIZ (Theory of Inventive Problem
Solving) and R&D strategy. Bridge the gap between the company's current
manufacturing capabilities and the extrapolated virtual alloy recipes.
Resolve technical contradictions (e.g. strength vs. weldability) using TRIZ
inventive principles.

Any validation finding with status "contradiction_found" is a problem Agent
X may have missed -- you MUST explicitly address each one in your roadmap
(e.g. "this recipe requires raising the Mn ceiling -- flagged for review"),
never silently build a recipe on top of it.

You are given Agent 2's full frontier-research report, not just the
extrapolated parameters Agent X derived from it. Use "materials_found" (full
comparator alloys from the literature) to ground your gap analysis in actual
competing/reference materials where available, not only the extrapolated
numbers. Also check "breakthrough_findings" for anything relevant that Agent
X's extrapolation didn't carry forward (e.g. a negative/neutral correlation
worth flagging as a risk, or a finding whose variable didn't resolve against
Agent X's range fields).

Use moderate creativity for cross-domain reasoning, but stay grounded in the
data you're given -- do not invent capabilities or constraints not present
in the input.

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "roadmap_markdown": "string, a full human-readable narrative roadmap in Markdown",
  "gaps": [{"description": "string", "contradiction": "string", "triz_principle": "string"}],
  "proposed_recipes": [{"grade_name": "string", "composition": {"<element>": <number>}, "source_extrapolation": "string"}],
  "roadmap_steps": [{"step": <number>, "action": "string", "owner": "string", "est_duration": "string"}]
}
"""

REQUIRED_OUTPUT_KEYS = ["roadmap_markdown", "gaps", "proposed_recipes", "roadmap_steps"]


class Agent3GapAnalysis:
  def __init__(self):
    self.client = get_anthropic_client()

  def run(
      self,
      agent_1_baseline_path: str,
      agent_2_report_path: str,
      agent_x_simulation_path: str,
      agent_v_validation_path: str,
      markdown_output_path: str = "agent_3_roadmap.md",
      json_output_path: str = "agent_3_roadmap.json",
  ) -> Dict[str, Any]:
    baseline = load_json_validated(agent_1_baseline_path, required_keys=["domains"])
    research = load_json_validated(
        agent_2_report_path, required_keys=["breakthrough_findings", "materials_found"]
    )
    simulation = load_json_validated(
        agent_x_simulation_path, required_keys=["extrapolated_parameters"]
    )
    validation = load_json_validated(agent_v_validation_path, required_keys=["findings"])

    contradictions = [f for f in validation["findings"] if f.get("status") == "contradiction_found"]
    if contradictions:
      logger.warning(
          "%d contradiction(s) from Agent V must be addressed in this roadmap.",
          len(contradictions),
      )

    # Agent 2/X/V are all scoped to the one domain picked at Checkpoint 1;
    # Agent 3 should be too. Passing Agent 1's *entire* baseline (every
    # domain, not just the selected one) burns tokens/cost on irrelevant
    # domains and makes output truncation more likely as a company's
    # portfolio grows. Fall back to the full baseline (with a warning)
    # rather than halting if the domain can't be found -- this is a
    # cost/quality optimization, not something worth failing the run over.
    domain_name = simulation.get("domain")
    selected_domain = next(
        (d for d in baseline.get("domains", []) if d.get("domain_name") == domain_name), None
    )
    if selected_domain is None:
      logger.warning(
          "Could not find domain '%s' in Agent 1's baseline; passing the "
          "full baseline to Agent 3 instead of just the selected domain.",
          domain_name,
      )
      scoped_baseline = baseline
    else:
      scoped_baseline = {"company": baseline.get("company"), "domains": [selected_domain]}

    user_message = f"""Here is the data for your analysis:

1. BASELINE MANUFACTURING PORTFOLIO (Agent 1), scoped to the selected domain:
{json.dumps(scoped_baseline, indent=2)}

2. FRONTIER RESEARCH -- FINDINGS & COMPARATOR MATERIALS (Agent 2):
{json.dumps(research, indent=2)}

3. EXTRAPOLATED ALLOY RECIPES (Agent X):
{json.dumps(simulation, indent=2)}

4. INDEPENDENT VALIDATION FINDINGS (Agent V):
{json.dumps(validation, indent=2)}

Generate a comprehensive Strategic Gap Analysis & R&D Roadmap covering:
1. Performance/process gaps between current production and simulated
   prototypes -- and against any comparator materials_found in (2).
2. Technical contradictions encountered (including every Agent V finding with
   status "contradiction_found" -- address each one by name).
3. Specific TRIZ principles applied to resolve these limitations.
4. An actionable, staged development roadmap.
"""

    def make_call():
      return self.client.messages.create(
          model=MODEL,
          # Needs room for a full Markdown narrative *and* three structured
          # JSON sections; 6000 was tight even before materials_found and
          # the broadened finding schema made the input larger too. Still
          # well under the non-streaming client timeout at this size.
          max_tokens=16000,
          system=SYSTEM_PROMPT,
          messages=[{"role": "user", "content": user_message}],
      )

    response = call_with_retry(make_call, label="Agent 3 gap analysis call")
    result = extract_json_object(extract_text(response))
    require_keys(result, REQUIRED_OUTPUT_KEYS, context="Agent 3 output")

    with open(markdown_output_path, "w", encoding="utf-8") as f:
      f.write(result["roadmap_markdown"])
    logger.info("Wrote narrative roadmap to '%s'.", markdown_output_path)

    structured = {k: result[k] for k in ("gaps", "proposed_recipes", "roadmap_steps")}
    save_json_validated(
        structured, json_output_path,
        required_keys=["gaps", "proposed_recipes", "roadmap_steps"],
    )

    return result


if __name__ == "__main__":
  agent_3 = Agent3GapAnalysis()
  agent_3.run(
      agent_1_baseline_path="temp_data/agent_1_baseline.json",
      agent_2_report_path="temp_data/agent_2_report.json",
      agent_x_simulation_path="temp_data/agent_x_simulation_results.json",
      agent_v_validation_path="temp_data/agent_v_validation.json",
      markdown_output_path="temp_data/agent_3_roadmap.md",
      json_output_path="temp_data/agent_3_roadmap.json",
  )
