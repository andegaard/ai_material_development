# AI Material Development

A multi-agent, Anthropic Claude-powered pipeline for steel alloy R&D. The
pipeline takes a company's public material portfolio, researches frontier
literature for a chosen steel domain, extrapolates candidate alloy recipes,
validates them against manufacturing constraints, and produces a strategic
roadmap plus an IP/sustainability audit — with a human checkpoint between
each major stage.

See [`agent_instructions.md`](agent_instructions.md) for the full agent
architecture, model assignments, JSON data contracts, and pipeline diagram.

## Status

All six agents plus the orchestrator are scaffolded against the v2 spec in
`agent_instructions.md`. **Not yet run against the real API** — see
"Before running" below for what needs checking first.

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
