"""
Agent 2: Frontier Research & Mechanism Hunter (v2)

Searches literature/patents for cutting-edge mechanisms in a chosen steel
domain, extracting composition ranges, phases, processing routes, and their
correlation with mechanical properties. Every finding must cite a source;
findings without one are dropped before Agent X ever sees them, per
agent_instructions.md section 2.
"""

import logging
from typing import Any, Dict

from common import (
    WEB_SEARCH_TOOL,
    call_with_retry,
    extract_json_object,
    extract_text,
    get_anthropic_client,
    require_sources,
    save_json_validated,
)

logging.basicConfig(level=logging.INFO, format="[Agent 2] %(message)s")
logger = logging.getLogger("agent_2")

MODEL = "claude-opus-5-5"
ESCALATED_MODEL = "claude-fable-5-1"  # for the most demanding synthesis cases

SYSTEM_PROMPT = """You are an academic metallurgist and trend analyst doing
open-ended frontier research. Explore broadly to catch "unknown unknowns",
but every claim must be grounded: cite at least one real source for every
finding.

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "domain": "string",
  "breakthrough_findings": [
    {
      "mechanism": "string",
      "performance_correlation": "positive | negative | neutral",
      "optimizing_variable": "string",
      "chemical_composition_range": {"<element>": {"min": <number>, "max": <number>}},
      "reported_mechanical_properties": {"...": "..."},
      "sources": [{"title": "string", "url": "string"}]
    }
  ]
}

Omit any finding you cannot cite at least one source for. Do not fabricate
sources.
"""

REQUIRED_OUTPUT_KEYS = ["domain", "breakthrough_findings"]


class Agent2FrontierResearch:
  def __init__(self, escalate: bool = False):
    self.client = get_anthropic_client()
    self.model = ESCALATED_MODEL if escalate else MODEL

  def run(self, domain: str, output_path: str = "agent_2_report.json") -> Dict[str, Any]:
    logger.info(
        "Researching frontier mechanisms for domain '%s' with %s...", domain, self.model
    )

    user_message = (
        f"Steel domain: {domain}\n\n"
        "Search literature and patents for cutting-edge mechanisms in this "
        "domain. Extract chemical composition ranges, microstructural "
        "phases, processing routes, and their correlation with mechanical "
        "properties."
    )

    def make_call():
      return self.client.messages.create(
          model=self.model,
          max_tokens=4000,
          system=SYSTEM_PROMPT,
          tools=[WEB_SEARCH_TOOL],
          messages=[{"role": "user", "content": user_message}],
      )

    response = call_with_retry(make_call, label="Agent 2 literature research call")
    result = extract_json_object(extract_text(response))

    result["breakthrough_findings"] = require_sources(
        result.get("breakthrough_findings", []), entry_label="finding"
    )

    save_json_validated(result, output_path, required_keys=REQUIRED_OUTPUT_KEYS)
    logger.info(
        "Wrote %d sourced finding(s) to '%s'.",
        len(result["breakthrough_findings"]), output_path,
    )
    return result


if __name__ == "__main__":
  agent_2 = Agent2FrontierResearch()
  agent_2.run(domain="Wear-Resistant Steels")
