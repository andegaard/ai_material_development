"""
Agent 1: Market Intelligence & Portfolio Architect (v2)

Maps a target company's public material portfolio into distinguishable
functional domains, then researches each grade within those domains in
depth: chemical composition, mechanical properties, phase composition, heat
treatment, manufacturing methods, product forms, ECO fingerprint, standards,
and applications. Every extracted fact must carry a source URL.

Two-phase design, not a single call:
  Phase A (`_discover_domains`) maps the company's domains and lists grade
  names within each -- cheap, breadth-first.
  Phase B (`_research_grade`) runs one dedicated research call per grade
  (capped at `MAX_GRADES_PER_DOMAIN` per domain) so each grade gets its own
  research budget instead of splitting one call's output across an entire
  domain's worth of grades. This is slower and costs more calls, but is far
  more likely to actually find chemistry/property data per grade than
  asking for everything in one shot.

Both phases are explicitly told to search the whole web relevant to the
company -- the company's own site is a starting point, not a boundary.
Distributor catalogs, standards bodies (EN/ISO/ASTM/SAE), academic papers,
patents, and press coverage are all fair game via the hosted `web_search`
tool; `web_fetch` pulls specific pages found that way.

Every grade record is normalized against `GRADE_TEMPLATE` before being
written out, so every material has the *same* set of fields even when a
field's value is unavailable (`null` / `[]`) for that particular grade --
this is what keeps downstream agents from having to special-case missing
keys per material.

Powder metallurgy (PM) is deliberately surfaced as its own deterministic
flag rather than left buried inside `manufacturing_methods` free text: PM
removes the segregation/solidification limits that cap conventional
ingot/wrought alloying and enables compositions and microstructures that
wouldn't otherwise be achievable, which matters directly to Agent 2's
research framing (see agent_2_frontier_research.py). `is_powder_metallurgy`
(per grade) and `includes_powder_metallurgy` (per domain) are computed in
code from `manufacturing_methods` after normalization -- not asked of the
model directly -- precisely so the flag can't go missing or drift out of
sync with what manufacturing_methods actually says. Both are tri-state
(`True` / `False` / `None`) since "no manufacturing-method data was found"
is a different situation from "we found data and it's not PM".
"""

import logging
from typing import Any, Dict, List, Optional

from common import (
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    PipelineHalt,
    call_with_retry,
    extract_json_object,
    extract_text,
    get_anthropic_client,
    save_json_validated,
)

logging.basicConfig(level=logging.INFO, format="[Agent 1] %(message)s")
logger = logging.getLogger("agent_1")

MODEL = "claude-sonnet-5"
MAX_GRADES_PER_DOMAIN = 15  # bounds cost/runtime for large catalogs; raise if needed

REQUIRED_OUTPUT_KEYS = ["company", "domains", "sources"]

# Every grade record is normalized to have exactly these keys. Nested dicts
# with fixed sub-fields (heat_treatment, eco_fingerprint) are normalized
# recursively; `chemical_composition`, `phase_composition`, and
# `mechanical_properties` are open-ended (keyed by whatever element/phase/
# property name is actually relevant to that grade -- not a fixed list
# decided in advance) and are left as whatever the model found, defaulting
# to {} rather than a fixed key set. A grade's mechanical properties should
# be whatever was actually reported for it, not forced into a predetermined
# set of property names some grades won't have data for and others might
# report under a different name entirely.
GRADE_TEMPLATE: Dict[str, Any] = {
    "grade_name": None,
    "chemical_composition": {},
    "mechanical_properties": {},
    "phase_composition": {},
    "heat_treatment": {
        "process": None,
        "austenitizing_temp_c": None,
        "quench_medium": None,
        "tempering_temp_c": None,
    },
    "manufacturing_methods": [],
    "product_forms": [],
    "eco_fingerprint": {
        "co2_kg_per_tonne": None,
        "recycled_content_pct": None,
        "energy_mj_per_tonne": None,
        "epd_available": None,
    },
    "standards_certifications": [],
    "applications": [],
    "notes": None,
    "sources": [],
}
# Not in GRADE_TEMPLATE on purpose: is_powder_metallurgy is derived from
# manufacturing_methods in code (see _derive_is_pm), not merged in from the
# model's own JSON like every other field above.


def _is_pm_method(method: Any) -> bool:
  """Matches 'powder metallurgy', 'PM', 'P/M', case-insensitively --
  whatever phrasing the model used for this manufacturing_methods entry.
  Not wrapped in the same try/except as the API call that produced this
  list, so a non-string entry (e.g. a stray null) here would otherwise
  crash this whole grade's processing, not just degrade it."""
  if not isinstance(method, str):
    return False
  normalized = method.strip().lower()
  return "powder" in normalized or normalized in ("pm", "p/m")


def _derive_is_pm(manufacturing_methods: List[str]) -> Optional[bool]:
  """True/False if we have manufacturing-method data to judge from, None if
  we don't -- collapsing "no data" into False would make an unresearched
  grade look like a confirmed non-PM grade."""
  if not manufacturing_methods:
    return None
  return any(_is_pm_method(m) for m in manufacturing_methods)

DISCOVERY_SYSTEM_PROMPT = """You are a precise market intelligence analyst for
industrial steel manufacturers. Work with low creativity and high factual
precision.

Do NOT limit yourself to the company's own web page -- it is a starting
point, not a boundary. Also search distributor/reseller catalogs, standards
bodies (EN, ISO, ASTM, SAE), academic literature, patents, and press
coverage that reference this company's products, to build the most complete
picture of their material portfolio that you can.

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "company": "string",
  "domains": [
    {
      "domain_name": "string",
      "domain_description": "string",
      "grades": ["string", "..."],
      "manufacturing_constraints": {"<element>": {"max": <number>, "unit": "wt%"}}
    }
  ],
  "sources": [{"title": "string", "url": "string"}]
}

List every grade you can find by name under its domain. You do not need
composition or property details yet -- a later pass researches each grade
individually. Every domain and grade you report must be traceable to at
least one entry in "sources".
"""

GRADE_DETAIL_SYSTEM_PROMPT = """You are a precise materials-data researcher.
Research ONE specific steel grade from ONE company in depth. Search broadly
across the web -- the company's own datasheets, distributor spec sheets,
standards documents (EN/ISO/ASTM/SAE), academic papers, and patents -- not
just the company's main page.

Extract every field you can find and cite. If you genuinely cannot find a
value for a field, leave it null (or an empty list/object) rather than
guessing, estimating, or carrying over a typical value from a similar grade.

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "grade_name": "string",
  "chemical_composition": {"<element>": {"min": <number|null>, "max": <number|null>, "unit": "wt%"}},
  "mechanical_properties": {"<property_name>": {"value": <number|null>, "unit": "string|null"}},
  "phase_composition": {"<phase_name>": <percent|null>},
  "heat_treatment": {
    "process": "string|null",
    "austenitizing_temp_c": <number|null>,
    "quench_medium": "string|null",
    "tempering_temp_c": <number|null>
  },
  "manufacturing_methods": ["string, e.g. hot_rolled | cold_rolled | cast | forged | powder_metallurgy | ingot"],
  "product_forms": ["string, e.g. plate | sheet | bar | tube"],
  "eco_fingerprint": {
    "co2_kg_per_tonne": <number|null>,
    "recycled_content_pct": <number|null>,
    "energy_mj_per_tonne": <number|null>,
    "epd_available": <true|false|null>
  },
  "standards_certifications": ["string, e.g. EN 10025-6"],
  "applications": ["string"],
  "notes": "string|null",
  "sources": [{"title": "string", "url": "string"}]
}

"mechanical_properties" is open-ended -- report whatever properties you
actually find for this grade, under whatever name makes sense for that
property (e.g. "yield_strength_mpa", "tensile_strength_mpa",
"elongation_pct", "hardness_hbw", "impact_toughness_j",
"fatigue_strength_mpa", "fracture_toughness_mpa_sqrt_m", "wear_rate", ...).
Do not force every grade into the same fixed set of properties -- some
grades will have data for properties others don't report at all, and that
difference is real information, not something to paper over.
"""


def _with_defaults(data: Optional[Dict[str, Any]], template: Dict[str, Any]) -> Dict[str, Any]:
  """Return `template`'s keys, with any values present in `data` overlaid on
  top, so every grade record has exactly the same keys whether or not the
  model found a value for each one."""
  data = data or {}
  result: Dict[str, Any] = {}
  for key, default in template.items():
    if isinstance(default, dict) and default:
      result[key] = _with_defaults(data.get(key), default)
    elif isinstance(default, dict):
      # An empty-dict default marks an open-ended field (chemical_composition,
      # phase_composition) whose sub-keys legitimately vary per grade --
      # pass through whatever the model found instead of recursing into a
      # fixed (and here, empty) template, which would otherwise wipe it out.
      result[key] = data.get(key) or {}
    else:
      result[key] = data.get(key, default)
  return result


class Agent1MarketIntelligence:
  def __init__(self, max_grades_per_domain: int = MAX_GRADES_PER_DOMAIN):
    self.client = get_anthropic_client()
    self.max_grades_per_domain = max_grades_per_domain

  def run(
      self, company: str, url: str, output_path: str = "agent_1_baseline.json"
  ) -> Dict[str, Any]:
    baseline = self._discover_domains(company, url)

    for domain in baseline.get("domains", []):
      grade_names: List[str] = domain.get("grades", [])
      if len(grade_names) > self.max_grades_per_domain:
        logger.warning(
            "Domain '%s' lists %d grades; researching only the first %d "
            "(MAX_GRADES_PER_DOMAIN=%d).",
            domain.get("domain_name"), len(grade_names),
            self.max_grades_per_domain, self.max_grades_per_domain,
        )
      grade_names = grade_names[: self.max_grades_per_domain]
      domain["grades"] = [self._research_grade(company, name) for name in grade_names]

      # Tri-state aggregate so Agent 2 can key off one domain-level field
      # instead of scanning every grade itself: True if any grade is
      # confirmed PM, None if the rest is simply unresearched (not a
      # confirmed "no"), False only if every grade was researched and none
      # of them are PM.
      pm_flags = [g.get("is_powder_metallurgy") for g in domain["grades"]]
      if any(f is True for f in pm_flags):
        domain["includes_powder_metallurgy"] = True
      elif any(f is None for f in pm_flags):
        domain["includes_powder_metallurgy"] = None
      else:
        domain["includes_powder_metallurgy"] = False

    save_json_validated(baseline, output_path, required_keys=REQUIRED_OUTPUT_KEYS)
    total_grades = sum(len(d.get("grades", [])) for d in baseline.get("domains", []))
    logger.info(
        "Wrote baseline for %d domain(s), %d grade(s) total, to '%s'.",
        len(baseline.get("domains", [])), total_grades, output_path,
    )
    return baseline

  def _discover_domains(self, company: str, url: str) -> Dict[str, Any]:
    logger.info("Mapping material portfolio for '%s' (%s)...", company, url)

    user_message = (
        f"Company: {company}\nMain web page: {url}\n\n"
        "Search this company's public material portfolio -- across the "
        "whole web, not just this page -- and map it into distinguishable "
        "functional domains, listing every grade name you can find under "
        "each."
    )

    def make_call():
      return self.client.messages.create(
          model=MODEL,
          max_tokens=3000,
          system=DISCOVERY_SYSTEM_PROMPT,
          tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL],
          messages=[{"role": "user", "content": user_message}],
      )

    response = call_with_retry(make_call, label="Agent 1 domain discovery call")
    return extract_json_object(extract_text(response))

  def _research_grade(self, company: str, grade_name: str) -> Dict[str, Any]:
    logger.info("Researching grade '%s'...", grade_name)

    user_message = (
        f"Company: {company}\nGrade: {grade_name}\n\n"
        "Research this specific grade in depth and fill in as much of the "
        "schema as you can find, with sources."
    )

    def make_call():
      return self.client.messages.create(
          model=MODEL,
          max_tokens=2000,
          system=GRADE_DETAIL_SYSTEM_PROMPT,
          tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL],
          messages=[{"role": "user", "content": user_message}],
      )

    try:
      response = call_with_retry(make_call, label=f"Agent 1 grade research call ({grade_name})")
      data = extract_json_object(extract_text(response))
    except PipelineHalt as exc:
      # A single grade's research failing shouldn't take down the whole
      # baseline -- record it as unavailable (all-null template) rather
      # than halting the entire company mapping over it.
      logger.warning("Could not research grade '%s': %s. Recording as unavailable.", grade_name, exc)
      data = {}

    data["grade_name"] = grade_name  # keep the discovered name as the join key
    grade = _with_defaults(data, GRADE_TEMPLATE)
    grade["is_powder_metallurgy"] = _derive_is_pm(grade["manufacturing_methods"])
    return grade


if __name__ == "__main__":
  agent_1 = Agent1MarketIntelligence()
  agent_1.run(company="SSAB", url="https://www.ssab.com")
