# AI Material Development

A multi-agent, Anthropic Claude-powered pipeline for steel alloy R&D. The
pipeline takes a company's public material portfolio, researches frontier
literature for a chosen steel domain, extrapolates candidate alloy recipes,
validates them against manufacturing constraints, and produces a strategic
roadmap plus an IP/sustainability audit — with a human checkpoint between
each major stage.

See [`agent_instructions.md`](agent_instructions.md) for the full agent
architecture, model assignments, JSON data contracts, and pipeline diagram.

## How to run

```bash
pip install -r requirements.txt
cp .env.example .env    # fill in a real ANTHROPIC_API_KEY

python orchestrator.py "Company Name" "https://company-website.com"
```

All output for that run is written to `runs/<sanitized company name>/`
(e.g. `runs/SSAB/`), including the final `pipeline_report.pdf`. Re-running
the same company name reuses (and overwrites) that same folder. You'll be
prompted twice during the run: once to pick a domain after Agent 1, once to
approve the roadmap after Agent 3 — see "Before running" below for API
details worth double-checking first.

### Estimated cost per run

Based on current published pricing (Agent 1/4 use `claude-sonnet-5` at
$2/$10 per MTok in/out, Agent 2/3 use `claude-opus-5-5` at $4/$20 per MTok;
Agent X/V/report-builder make no API calls at all):

| Company size | Agent 1 calls | Agent 2 calls | Rough total |
|---|---|---|---|
| Small (1-2 domains, ~8 grades total) | ~9 | ~9 (1 planning + ~8 topics) | **~$1** |
| Medium (3 domains, ~30 grades total) | ~31 | ~16 (capped at 15 topics) | **~$2** |
| Large (5+ domains, 75+ grades, capped at 15/domain) | ~76 | ~16 (same cap — only the one selected domain) | **~$3-4** |

**Agent 1 is the dominant, most variable cost** — it runs one research call
per grade, per domain (capped at `MAX_GRADES_PER_DOMAIN=15`), for *every*
domain it finds, not just the one you'll eventually select. A company with
a broad portfolio costs noticeably more to map than one with a narrow one.
Agent 2 is comparatively fixed since it only ever researches the one domain
picked at Checkpoint 1.

Take these numbers as directional, not precise, for two reasons: (1) the
`web_search` tool's ingested search results count as input tokens and are
not bounded by `max_tokens` the way output is, so actual input token usage
per call is genuinely hard to predict without running it; (2) a per-search
tool fee may apply on top of token costs — check your Anthropic console's
usage page for the confirmed figure. For a precise estimate before a real
run, use `client.messages.count_tokens()` on a representative prompt, or
just run once against a real company and read `response.usage` to calibrate
the numbers above.

## Status

All six agents plus the orchestrator are scaffolded against the v2 spec in
`agent_instructions.md`. **Not yet run against the real API** — see
"Before running" below for what needs checking first.

### Progress log

**Done:**
- Repo hygiene: v1 prototype moved to `archive/v1_prototype/`, `.gitignore`
  added, stray `.DS_Store` files untracked.
- All six agents + orchestrator scaffolded from `agent_instructions.md`,
  sharing cross-cutting policy in `common.py` (retry-with-backoff, JSON
  validation, `PipelineHalt`, source-citation filtering).
- **Agent 1** reworked into two phases: cheap domain+grade-name discovery,
  then one dedicated research call per grade (capped at 15/domain) covering
  chemical composition, mechanical properties, phase composition, heat
  treatment, manufacturing methods, product forms, ECO fingerprint,
  standards, applications. Both phases explicitly search the whole web, not
  just the company's own page. Every grade is normalized against a fixed
  template (`GRADE_TEMPLATE`) so every material has the same *topics* even
  when a topic's data is unavailable (`null`/`[]`) — not the same chemical
  elements, since that legitimately varies per alloy.
- **Agent 2** reworked into two phases: a planning call grounded in Agent
  1's actual domain data derives explicit `performance_priorities`
  (property, direction, rationale — what "good" means for this domain) and
  a list of research sub-topics drawn from the domain's real alloy systems;
  then one exhaustive `web_search` call per sub-topic (capped at 15),
  findings tagged with their source topic, unsourced findings dropped.
- **Domain-scoping bug fixed**: `extract_manufacturing_constraints()` used
  to merge every domain's constraints together, so two domains with
  different limits for the same element could silently overwrite each
  other. Agent X now resolves and records the domain it ran for in its own
  output; Agent V picks up that same domain automatically. Verified with a
  conflicting-limits test.
- **Agent X broadened** beyond chemistry-only: findings' `optimizing_variable`
  is now resolved against chemical composition, phase composition,
  heat-treatment, *and mechanical-property* ranges (`variable_category` tags
  which). Phase fractions are clamped at 100%. Non-chemical variables get
  constraint status `not_applicable` (Agent 1 has no constraints of that
  kind) rather than the misleading `no_constraint_found`. Agent V updated
  to match.
- **Mechanical properties made open-ended, everywhere.** Agent 1's
  `mechanical_properties` was a hardcoded fixed key list (yield/tensile/
  hardness/...) — now it's keyed by whatever property name was actually
  found per grade, same treatment as `chemical_composition`/
  `phase_composition` already had. Agent 2 gained a `mechanical_property_range`
  finding field (parallel to the chemical/phase/heat-treatment ones) for
  when the literature trend *is* a mechanical property varying across
  trials, distinct from `reported_mechanical_properties` (a single value at
  the tested condition — grounding context, not a range to extrapolate).
  Agent X now carries that context through onto every extrapolated
  parameter as `literature_reported_properties` instead of silently
  dropping it. `report_builder.py` updated to render the open-ended
  property set as one flexible column instead of fixed Yield/Tensile/
  Hardness columns.
- **Swappable simulation engine**: `SimulationEngine` interface added,
  `HeuristicLinearEngine` (flat +15% rule) is the only implementation today.
  `CalphadEngine` is a documented, unimplemented stub — dropping in real
  thermodynamics later (pycalphad, or Thermo-Calc TC-Python if a license is
  available) is a matter of implementing that one class and passing
  `AgentXSimulator(engine=CalphadEngine(...))`; nothing else in the
  pipeline needs to change. (Explored actually wiring pycalphad in; decided
  to hold off until it's clear whether a Thermo-Calc license is obtainable,
  since TC-Python's database coverage for multicomponent steel is far
  broader than any free option.)
- **Powder metallurgy (PM) surfaced as a key signal**: `is_powder_metallurgy`
  (per grade) and `includes_powder_metallurgy` (per domain) are derived in
  code from `manufacturing_methods`, tri-state (`True`/`False`/`None` for
  "not yet researched"). Agent 2's planning prompt treats this as a key
  factor — PM removes conventional ingot/wrought alloying limits, so
  research topics and priorities should reflect that.
- **Agent V, 3, 4 walked through in detail** (role, input, output) — see
  conversation history; no code changes needed, they already matched intent.
- **Closed a real data-loss gap between Agent 2 and Agent 3.** Agent 3 only
  ever received Agent X's narrowed extrapolation output, never Agent 2's
  full report — so any finding Agent X's per-variable logic didn't pick up
  (a neutral/negative correlation worth noting, richer literature context)
  silently never reached the roadmap stage. Agent 3 now takes
  `agent_2_report_path` as a fourth input and reasons over the full
  research report alongside Agent 1/X/V's data.
- **Comparator materials**: Agent 2's finding schema is mechanism-centric
  (one correlation, a few named variable ranges), which flattened a
  different common case — a paper describing a *complete* alloy (full
  composition/properties/phases/heat-treatment), not just one trend. Added
  a parallel `materials_found` list (shaped like Agent 1's own grade
  record) for exactly that, aggregated and source-filtered the same way as
  `breakthrough_findings`. Not passed to Agent X (nothing there to
  extrapolate — it's reference data) but passed to Agent 3, and rendered in
  `report_builder.py`'s Section 1.
- **Consolidated PDF report** (`report_builder.py`): reads whatever stage
  output files exist and renders one PDF with a section per
  Agent-1&2/Agent-X&V/Agent-3/Agent-4. Tolerant of a partial run — a stage
  that hasn't produced output yet is labeled "not yet run" rather than
  crashing the report. Wired into `orchestrator.py`: builds automatically
  at the end of a full run, and also on any `PipelineHalt` so a rejected/
  halted run still produces a report of whatever did complete.
- **Runnable from the command line, per-company output folders.**
  `orchestrator.py` was hardcoded to always run SSAB with no way to target
  another company. Now takes `company`/`company_url` as CLI args and writes
  everything to `runs/<sanitized company name>/` instead of a fixed
  `temp_data/` — each company's project data stays in its own folder, and
  re-running a company reuses (overwrites) its own folder rather than
  colliding with another's. Verified end to end with a fully mocked run
  (company name with spaces/punctuation correctly sanitized to a safe
  directory name, all output including the PDF landing in that folder).

**Explicitly not done / honest limitations:**
- No real thermodynamic computation anywhere. `heuristic_linear_extrapolation`
  is a flat percentage rule, not physics. `simulated_phase_fraction` and
  `required_cooling_rate_c_s` in Agent X's output are still `null`.
- Nothing has been run against the live Anthropic API yet — Agents 1, 2, 3,
  4 are untested beyond code review and compile checks (Agent X, Agent V,
  and `report_builder.py` don't need the API and have been exercised with
  mock data).
- See "Before running" below for the API-integration specifics (tool-type
  strings, model IDs, structured outputs) still needing verification.

### Next steps (pick up here)

1. Review `orchestrator.py` end to end now that all agents + the report
   builder are wired together.
2. Resolve the "Before running" items, then do a real end-to-end run with a
   live `ANTHROPIC_API_KEY` against a real company/domain.
3. Once a real run exists, sanity-check `report_builder.py`'s output against
   actual (not mock) data — table column choices and the markdown-lite
   renderer were only exercised against hand-written stand-ins for Agent
   3/4's prose.

## Layout

- `agent_instructions.md` — current (v2) pipeline specification.
- `common.py` — shared helpers: retry-with-backoff, JSON load/validate,
  Anthropic client, JSON extraction from model output, the source-citation
  and manufacturing-constraint-extraction policies shared by multiple agents.
- `agent_1_market_intelligence.py` — Agent 1 (market/portfolio mapping).
- `agent_2_frontier_research.py` — Agent 2 (literature/patent research).
- `agent_x_simulator.py` — Agent X (heuristic extrapolation, no LLM call).
- `agent_v_validator.py` — Agent V (independent constraint re-check, pure code).
- `agent_3_gap_analysis.py` — Agent 3 (TRIZ gap analysis + roadmap).
- `agent_4_ip_lca_audit.py` — Agent 4 (FTO screen + LCA estimate).
- `report_builder.py` — consolidates all stage outputs into one PDF report.
- `orchestrator.py` — runs the full pipeline with both human checkpoints.
- `archive/v1_prototype/` — earlier prototype (v1), kept for reference. Uses
  retired model IDs and deprecated temperature parameters; superseded by the
  v2 spec above.

## Before running

Things flagged in the code that should be checked against current docs
before the first real run, rather than assumed:

- **`WEB_SEARCH_TOOL` / `WEB_FETCH_TOOL` in `common.py`** — the hosted
  server-tool type strings (`web_search_20250305`, `web_fetch_20250910`) are
  a best guess as of when this was written and need confirming against the
  current Anthropic API docs; these version-dated strings change between
  API releases.
- **`claude-fable-5-1` escalation path in Agent 2** — confirm this model ID
  and that escalating mid-pipeline (vs. always using it) is the right call.
- **JSON-via-prompt vs. structured outputs** — every agent currently asks
  the model to emit a ` ```json ` fence and parses it out
  (`common.extract_json_object`). Worth checking whether the API now offers
  a more reliable structured-output mode instead.
- **`max_tokens` per agent** — set to plausible round numbers, not tuned.
- **Agent X's simulation engine** — no real thermodynamics yet. Extrapolation
  is a flat +15% linear rule (`HeuristicLinearEngine`), across chemical
  composition, phase composition, and heat-treatment findings, labeled
  `heuristic_linear_extrapolation`. A `SimulationEngine` interface exists so
  a real engine can be swapped in later without restructuring the pipeline
  (`CalphadEngine` is the documented, unimplemented stub) — see
  `agent_x_simulator.py`'s module docstring for what that would need
  (a Thermo-Calc TC-Python license, or `pycalphad` plus a thermodynamic
  database for the relevant alloy system).
- **Setup**: `pip install -r requirements.txt`, then copy `.env.example` to
  `.env` and fill in a real `ANTHROPIC_API_KEY`.
