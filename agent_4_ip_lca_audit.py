"""
Agent 4: IP-Freedom & Life Cycle Assessment (LCA) Optimizer (v2)

Screens Freedom-to-Operate (FTO) risk via public patent search and estimates
CO2/energy footprint for each proposed manufacturing route.

Scope limitation (see agent_instructions.md section 5): this is a
preliminary public-patent screening, not a legal FTO opinion. Any recipe
flagged as promising must be routed to a qualified patent attorney before
commercial commitment.
"""

import json
import logging
from typing import Any, Dict

from common import (
    WEB_SEARCH_TOOL,
    call_with_retry,
    extract_json_object,
    extract_text,
    get_anthropic_client,
    load_json_validated,
    save_json_validated,
)

logging.basicConfig(level=logging.INFO, format="[Agent 4] %(message)s")
logger = logging.getLogger("agent_4")

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a patent-screening and sustainability analyst
performing rigid, factual auditing. You are NOT a patent attorney and this
is NOT a legal Freedom-to-Operate (FTO) opinion -- it is a preliminary
public-patent screening only. State this limitation explicitly in your
output, and route any recipe you flag as promising to
"requires_legal_review".

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "scope_note": "string, stating this is a preliminary screening, not a legal FTO opinion",
  "fto_screen": [{"grade_name": "string", "public_patent_hits": ["string"], "risk_note": "string", "sources": [{"title": "string", "url": "string"}]}],
  "lca_estimate": {"<grade_name>": {"co2_kg_per_tonne_estimate": <number>, "energy_mj_per_tonne_estimate": <number>, "basis": "string"}},
  "requires_legal_review": ["string (grade names flagged as promising)"]
}
"""

REQUIRED_OUTPUT_KEYS = ["scope_note", "fto_screen", "lca_estimate", "requires_legal_review"]


class Agent4IPAndLCAAudit:
  def __init__(self):
    self.client = get_anthropic_client()

  def run(
      self,
      agent_3_roadmap_json_path: str,
      markdown_output_path: str = "agent_4_audit.md",
      json_output_path: str = "agent_4_audit.json",
  ) -> Dict[str, Any]:
    roadmap = load_json_validated(agent_3_roadmap_json_path, required_keys=["proposed_recipes"])

    user_message = f"""Here are the proposed alloy recipes and roadmap approved
at the human checkpoint:

{json.dumps(roadmap, indent=2)}

For each proposed recipe:
1. Search public patent literature for potential Freedom-to-Operate conflicts.
2. Estimate CO2/energy footprint for its manufacturing route.
3. Flag any recipe that looks promising for a real legal FTO review.

Remember: this is a preliminary screening, not a legal opinion.
"""

    def make_call():
      return self.client.messages.create(
          model=MODEL,
          max_tokens=4000,
          system=SYSTEM_PROMPT,
          tools=[WEB_SEARCH_TOOL],
          messages=[{"role": "user", "content": user_message}],
      )

    response = call_with_retry(make_call, label="Agent 4 FTO/LCA audit call")
    result = extract_json_object(extract_text(response))

    save_json_validated(result, json_output_path, required_keys=REQUIRED_OUTPUT_KEYS)

    with open(markdown_output_path, "w", encoding="utf-8") as f:
      f.write(self._render_markdown(result))
    logger.info("Wrote audit narrative to '%s'.", markdown_output_path)

    return result

  @staticmethod
  def _render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# IP-Freedom & LCA Audit",
        "",
        f"> {result.get('scope_note', 'Preliminary screening only -- not a legal FTO opinion.')}",
        "",
        "## Freedom-to-Operate Screen",
    ]
    for entry in result.get("fto_screen", []):
      lines.append(f"### {entry.get('grade_name', 'Unnamed grade')}")
      lines.append(entry.get("risk_note", ""))
      for hit in entry.get("public_patent_hits", []):
        lines.append(f"- {hit}")
      lines.append("")

    lines.append("## LCA Estimate")
    for grade, est in result.get("lca_estimate", {}).items():
      lines.append(
          f"- **{grade}**: {est.get('co2_kg_per_tonne_estimate')} kg CO2/t, "
          f"{est.get('energy_mj_per_tonne_estimate')} MJ/t ({est.get('basis')})"
      )
    lines.append("")

    lines.append("## Requires Legal Review")
    for grade in result.get("requires_legal_review", []):
      lines.append(f"- {grade}")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
  agent_4 = Agent4IPAndLCAAudit()
  agent_4.run(
      agent_3_roadmap_json_path="temp_data/agent_3_roadmap.json",
      markdown_output_path="temp_data/agent_4_audit.md",
      json_output_path="temp_data/agent_4_audit.json",
  )
