"""
Agent 2: Frontier Research & Mechanism Hunter (v2)

Two-phase design, mirroring Agent 1's per-grade pattern:

  Phase A (`_plan_research`) is grounded in Agent 1's actual data for the
  selected domain -- its description, current grades, their chemistry and
  mechanical properties -- and from that derives:
    - `performance_priorities`: which properties actually define success in
      this domain and which direction is better for each, with a stated
      rationale. This is what tells the rest of the pipeline what "good"
      means for e.g. a Wear-Resistant domain (hardness up) versus a
      High-Strength Structural one (yield strength up, weldability
      preserved) -- instead of that judgment staying implicit in the model's
      head.
    - `research_topics`: a broad, non-redundant list of distinct mechanisms
      / alloying strategies / processing routes worth investigating, derived
      from the real alloy systems Agent 1 already found for this domain
      rather than guessed cold. If Agent 1 flagged the domain as including
      powder-metallurgy (PM) grades (`includes_powder_metallurgy` /
      `is_powder_metallurgy` -- see agent_1_market_intelligence.py), that's
      treated as a key factor here: PM removes conventional ingot/wrought
      alloying limits, so both the priorities and the topics should reflect
      compositions/microstructures that wouldn't be realistic otherwise.

  Phase B (`_research_topic`) runs one dedicated, `web_search`-heavy call
  per topic (capped at `MAX_RESEARCH_TOPICS_PER_DOMAIN`), each told to keep
  issuing new search queries on that specific sub-topic until it has
  surfaced the distinct findings/sources actually available -- this
  decomposition, not a single broad call, is what gets meaningfully broader
  literature coverage than "the first 5 hits". No search-based approach can
  read literally everything ever published; running many focused calls
  instead of one is the real lever available here.

Every finding is tagged with the sub-topic that produced it (for
traceability) and must carry at least one source -- unsourced findings are
dropped before Agent X ever sees them, per agent_instructions.md section 2.

Each finding may report a chemical_composition_range, a
phase_composition_range, a heat_treatment_range, and/or a
mechanical_property_range -- Agent X extrapolates across whichever of these
actually apply to a given finding, not just chemistry. Mechanical properties
aren't a fixed list decided in advance here either: report whatever
properties the literature actually gives you, under whatever name fits.
Separately, a finding's reported_mechanical_properties (a single reported
value at the tested condition, not a range) is carried through to Agent X
as grounding context rather than something to extrapolate.

Findings are mechanism-centric: one correlation, up to four range fields
tied to named variables. That flattens a different, common case -- a paper
describing a *complete* comparator alloy (full composition, properties,
phases, heat treatment) rather than a single mechanism trend. Those go in a
separate `materials_found` list, shaped like Agent 1's own grade record, so
a real alloy a company doesn't currently make isn't squeezed into a
one-variable-at-a-time schema just because that's what findings use.
`materials_found` isn't passed to Agent X (there's nothing there to
extrapolate -- it's reference data, not a trend), but it is passed to
Agent 3 (along with this entire report, not just what Agent X extracted
from it) so the gap-analysis stage can reason over genuine comparator
materials and findings Agent X's narrow per-variable logic didn't pick up.
"""

import json
import logging
from typing import Any, Dict, List, Tuple

from common import (
    WEB_SEARCH_TOOL,
    PipelineHalt,
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
MAX_RESEARCH_TOPICS_PER_DOMAIN = 15  # bounds cost/runtime; raise if needed

REQUIRED_OUTPUT_KEYS = [
    "domain", "performance_priorities", "research_topics_investigated",
    "breakthrough_findings", "materials_found",
]

PLANNING_SYSTEM_PROMPT = """You are an academic metallurgist and trend
analyst planning a frontier-research scan for one specific steel domain.

You are given the company's own current portfolio data for this domain:
its description, its existing grades, and their known chemistry and
mechanical properties. Use this as your baseline -- what "improvement" means
here is "better than what these current grades already achieve".

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "performance_priorities": [
    {"property": "string", "direction": "maximize | minimize | balance", "rationale": "string"}
  ],
  "research_topics": ["string", "..."]
}

1. "performance_priorities": identify the properties that actually define
   success in this domain, and which direction is better for each. Ground
   this explicitly in the domain description and the current grades' own
   properties -- do not just assert a generic answer.
2. "research_topics": propose a broad, non-redundant list of distinct
   mechanisms, alloying strategies, or processing routes worth investigating
   to improve on those priorities beyond the current grades. Draw on the
   real alloy systems already present in the current grades' chemistry
   rather than generic topics unrelated to what this company actually makes.

If the domain data shows `includes_powder_metallurgy: true` (at the domain
level) or any grade has `is_powder_metallurgy: true`, treat that as a key
factor, not an incidental detail: powder metallurgy removes the
segregation/solidification limits that cap what conventional ingot/wrought
alloying can achieve, and enables consolidation routes (sintering, HIP),
compositions, and controlled microstructures/porosity that wouldn't
otherwise be realistic. In that case, your research_topics should include
PM-specific directions (e.g. powder chemistry/atomization, consolidation
parameters, achievable density) where relevant, and your
performance_priorities/mechanisms should not be limited to what's achievable
via conventional ingot metallurgy alone.
"""

TOPIC_SYSTEM_PROMPT = """You are an academic metallurgist doing an
exhaustive literature and patent search on ONE specific, narrow sub-topic
within a steel domain. Keep issuing new search queries with different
phrasings and angles until you have surfaced the distinct findings and
sources actually available on this sub-topic -- do not stop after the first
one or two hits. Every claim must be grounded: cite at least one real source
for every finding.

Output ONLY a single JSON object (in a ```json code fence) matching exactly
this schema, with no other commentary:

{
  "findings": [
    {
      "mechanism": "string",
      "performance_correlation": "positive | negative | neutral",
      "optimizing_variable": "string, or [string, ...] -- may name a chemical element, a microstructural phase, a heat-treatment parameter, OR a mechanical property itself when that's what the literature reports a range/trend for",
      "chemical_composition_range": {"<element>": {"min": <number>, "max": <number>}},
      "phase_composition_range": {"<phase_name>": {"min": <percent>, "max": <percent>}},
      "heat_treatment_range": {"<parameter_name, e.g. tempering_temp_c or cooling_rate_c_s>": {"min": <number>, "max": <number>, "unit": "string"}},
      "mechanical_property_range": {"<property_name, whatever you actually found>": {"min": <number>, "max": <number>, "unit": "string"}},
      "reported_mechanical_properties": {"<property_name>": {"value": <number>, "unit": "string"}},
      "sources": [{"title": "string", "url": "string"}]
    }
  ],
  "materials_found": [
    {
      "material_name": "string -- the specific alloy/grade name as reported, or a descriptive label if the paper didn't name it",
      "chemical_composition": {"<element>": {"min": <number|null>, "max": <number|null>, "unit": "wt%"}},
      "mechanical_properties": {"<property_name>": {"value": <number|null>, "unit": "string|null"}},
      "phase_composition": {"<phase_name>": <percent|null>},
      "heat_treatment": {"process": "string|null", "austenitizing_temp_c": <number|null>, "quench_medium": "string|null", "tempering_temp_c": <number|null>},
      "manufacturing_methods": ["string"],
      "notes": "string|null",
      "sources": [{"title": "string", "url": "string"}]
    }
  ]
}

"mechanical_property_range" vs. "reported_mechanical_properties" are
different things: use "mechanical_property_range" when the mechanism's
own trend IS a mechanical property varying across trials (e.g. hardness
ranged 380-420 HBW across the compositions tested) -- this makes that
property itself an optimizable target. Use "reported_mechanical_properties"
for a single reported data point at the tested condition (e.g. "at this
composition, yield strength was X") -- this is grounding context, not a
range to push beyond.

Judge "performance_correlation" against the performance priorities you are
given, not a generic notion of "better". Report as many distinct findings as
you can actually source -- do not pad with duplicates or invent findings you
cannot cite. Omit any finding you cannot cite at least one source for.

Include whichever of "chemical_composition_range", "phase_composition_range",
"heat_treatment_range", and "mechanical_property_range" are actually
relevant and sourced for a given finding -- you do not need to fill all four
for every finding, and should leave a range object out entirely if you have
no sourced data for it.

"findings" vs. "materials_found" capture different things. A "finding" is
one mechanism/trend (one correlation, a variable or two, a range). Use
"materials_found" instead when a source describes a *complete* specific
alloy in enough detail to be worth recording as its own material record
(composition, properties, phases, heat treatment) -- e.g. a competitor
grade, a research alloy, or a named variant from a review paper. Don't
force a rich material description into a single-variable finding just
because that's the other schema available; don't invent a materials_found
entry from a finding that only reports one variable's range either. Leave
materials_found empty for this topic if nothing in the literature actually
warrants a full material record.
"""


class Agent2FrontierResearch:
  def __init__(self, escalate: bool = False, max_topics_per_domain: int = MAX_RESEARCH_TOPICS_PER_DOMAIN):
    self.client = get_anthropic_client()
    self.model = ESCALATED_MODEL if escalate else MODEL
    self.max_topics_per_domain = max_topics_per_domain

  def run(self, domain: Dict[str, Any], output_path: str = "agent_2_report.json") -> Dict[str, Any]:
    domain_name = domain.get("domain_name", "unknown domain")
    logger.info("Planning research for domain '%s' with %s...", domain_name, self.model)

    plan = self._plan_research(domain)
    priorities = plan.get("performance_priorities", [])
    topics = plan.get("research_topics", [])

    if len(topics) > self.max_topics_per_domain:
      logger.warning(
          "Planning proposed %d research topics; investigating only the "
          "first %d (max_topics_per_domain=%d).",
          len(topics), self.max_topics_per_domain, self.max_topics_per_domain,
      )
    topics = topics[: self.max_topics_per_domain]

    all_findings: List[Dict[str, Any]] = []
    all_materials: List[Dict[str, Any]] = []
    for topic in topics:
      findings, materials = self._research_topic(domain_name, topic, priorities)
      all_findings.extend(findings)
      all_materials.extend(materials)

    all_findings = require_sources(all_findings, entry_label="finding")
    all_materials = require_sources(all_materials, entry_label="material")

    result = {
        "domain": domain_name,
        "performance_priorities": priorities,
        "research_topics_investigated": topics,
        "breakthrough_findings": all_findings,
        "materials_found": all_materials,
    }
    save_json_validated(result, output_path, required_keys=REQUIRED_OUTPUT_KEYS)
    logger.info(
        "Wrote %d sourced finding(s) and %d comparator material(s) across "
        "%d topic(s) to '%s'.",
        len(all_findings), len(all_materials), len(topics), output_path,
    )
    return result

  def _plan_research(self, domain: Dict[str, Any]) -> Dict[str, Any]:
    user_message = (
        "Here is the company's current portfolio data for this domain:\n\n"
        + json.dumps(domain, indent=2)
        + "\n\nIdentify the domain's performance priorities and propose a "
        "research topic list, per your instructions."
    )

    def make_call():
      return self.client.messages.create(
          model=self.model,
          max_tokens=2000,
          system=PLANNING_SYSTEM_PROMPT,
          messages=[{"role": "user", "content": user_message}],
      )

    response = call_with_retry(make_call, label="Agent 2 research planning call")
    return extract_json_object(extract_text(response))

  def _research_topic(
      self, domain_name: str, topic: str, priorities: List[Dict[str, Any]]
  ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    logger.info("Researching sub-topic '%s'...", topic)

    user_message = (
        f"Domain: {domain_name}\nSub-topic: {topic}\n\n"
        f"Performance priorities for this domain:\n{json.dumps(priorities, indent=2)}\n\n"
        "Exhaustively search literature and patents on this specific sub-topic."
    )

    def make_call():
      return self.client.messages.create(
          model=self.model,
          max_tokens=3000,
          system=TOPIC_SYSTEM_PROMPT,
          tools=[WEB_SEARCH_TOOL],
          messages=[{"role": "user", "content": user_message}],
      )

    try:
      response = call_with_retry(make_call, label=f"Agent 2 topic research call ({topic})")
      data = extract_json_object(extract_text(response))
    except PipelineHalt as exc:
      logger.warning("Could not research sub-topic '%s': %s. Skipping.", topic, exc)
      return [], []

    findings = data.get("findings", [])
    for finding in findings:
      finding["research_topic"] = topic

    materials = data.get("materials_found", [])
    for material in materials:
      material["research_topic"] = topic

    return findings, materials


if __name__ == "__main__":
  mock_domain = {
      "domain_name": "Wear-Resistant Steels",
      "domain_description": "Steels for abrasive wear applications such as buckets, chutes, and crushing equipment.",
      "manufacturing_constraints": {"Mn": {"max": 1.6, "unit": "wt%"}},
      "grades": [{
          "grade_name": "Wear-Resistant 400",
          "chemical_composition": {"C": {"min": 0.2, "max": 0.3, "unit": "wt%"}},
          "mechanical_properties": {"hardness": {"value": 400, "scale": "HBW"}},
      }],
  }
  agent_2 = Agent2FrontierResearch()
  agent_2.run(mock_domain)
