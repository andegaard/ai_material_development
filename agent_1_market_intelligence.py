"""
Agent 1: Market Intelligence & Portfolio Architect (v2)

Maps a target company's public material portfolio into distinguishable
functional domains (e.g. Wear-Resistant, High-Strength Structural, Tool
Steels), with every extracted fact carrying a source URL. Uses the
Anthropic hosted `web_search` / `web_fetch` tools so retrieval is grounded
instead of hallucinated, per agent_instructions.md section 1.
"""

import logging
from typing import Any, Dict

from common import (
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    call_with_retry,
    extract_json_object,
    extract_text,
    get_anthropic_client,
    save_json_validated,
)

logging.basicConfig(level=logging.INFO, format="[Agent 1] %(message)s")
logger = logging.getLogger("agent_1")

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a precise market intelligence analyst for industrial
steel manufacturers. Work with low creativity and high factual precision:
only report what you can find and cite from public web sources (the
company's own site, spec sheets, press releases, published datasheets).
Never invent a grade, domain, or constraint you cannot cite.

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "company": "string",
  "domains": [
    {
      "domain_name": "string",
      "grades": ["string"],
      "manufacturing_constraints": {"<element>": {"max": <number>, "unit": "wt%"}}
    }
  ],
  "sources": [{"title": "string", "url": "string"}]
}

Every domain and grade you report must be traceable to at least one entry in
"sources". If you cannot find manufacturing constraints for a domain, omit
that domain's "manufacturing_constraints" entries rather than guessing.
"""

REQUIRED_OUTPUT_KEYS = ["company", "domains", "sources"]


class Agent1MarketIntelligence:
  def __init__(self):
    self.client = get_anthropic_client()

  def run(
      self, company: str, url: str, output_path: str = "agent_1_baseline.json"
  ) -> Dict[str, Any]:
    logger.info("Mapping material portfolio for '%s' (%s)...", company, url)

    user_message = (
        f"Company: {company}\nMain web page: {url}\n\n"
        "Search this company's public material portfolio and map it into "
        "distinguishable functional domains, with example grades and any "
        "manufacturing constraints (element composition limits) you can "
        "find and cite."
    )

    def make_call():
      return self.client.messages.create(
          model=MODEL,
          max_tokens=4000,
          system=SYSTEM_PROMPT,
          tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL],
          messages=[{"role": "user", "content": user_message}],
      )

    response = call_with_retry(make_call, label="Agent 1 web research call")
    result = extract_json_object(extract_text(response))

    save_json_validated(result, output_path, required_keys=REQUIRED_OUTPUT_KEYS)
    logger.info(
        "Wrote baseline for %d domain(s) to '%s'.",
        len(result.get("domains", [])), output_path,
    )
    return result


if __name__ == "__main__":
  agent_1 = Agent1MarketIntelligence()
  agent_1.run(company="SSAB", url="https://www.ssab.com")
