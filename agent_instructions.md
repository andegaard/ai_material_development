# Multi-Agent R&D System Instructions v2: Anthropic-Powered Steel Innovation Pipeline

This document defines the agent architecture, model configuration, tool integration,
data contracts (JSON schemas), validation steps, and human checkpoints for the
autonomous steel research and development system.

Changelog vs. v1:
- All model IDs updated to currently-active models (the v1 IDs are retired).
- Pipeline order clarified: Agent 2 -> Agent X -> **Agent V (new: validator)** -> Agent 3 -> Agent 4.
- Agent 1 and Agent 2 now specify the `web_search` tool explicitly — v1 assumed
  "autonomous crawling" / "scanning literature" without giving the model any way
  to actually reach the web, which invites hallucinated data.
- Every agent now has an explicit JSON output schema, not just a filename.
- Added Agent V, an independent validator that checks Agent X's extrapolated
  recipes against Agent 1's manufacturing constraints before Agent 3 builds a
  roadmap on top of them.
- Added a second human checkpoint after Agent 3, before Agent 4 / any lab work.
- Added error-handling / retry policy and a note on the `temperature` parameter
  deprecation on newer models.

---

## Global System Configuration & Model Strategy

* **Core LLM Provider:** Anthropic Claude API (Messages API). Agents 1 and 2 use
  the built-in `web_search` tool for grounded, cited retrieval; consider
  [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)
  (beta) instead of a hand-rolled loop if you want a managed sandbox with
  web search/fetch, file I/O and long-running/async execution built in.
* **Design Philosophy:** Niche-optimized models balancing extreme structural
  fidelity (data parsing, numeric extrapolation) with deep analogical reasoning
  (frontier research synthesis, strategic gap analysis).
* **Data contracts:** every agent emits a JSON file matching the schema given
  below, in addition to any human-readable Markdown narrative. Downstream
  agents consume the JSON, never the prose. Validate each JSON output against
  its schema before writing it to disk; on validation failure, halt the
  pipeline rather than passing malformed data forward.
* **Model parameter note:** `temperature`/`top_p`/`top_k` are deprecated on
  Claude 4.7-generation models and later (the API returns an error if you set
  them to a non-default value). Where noted below as "steer via prompt", give
  the desired determinism/creativity as an instruction in the system prompt
  instead of a temperature override, and confirm current behavior for your
  chosen model in the docs before shipping.
* **Error handling:** every LLM call is wrapped in a retry with exponential
  backoff (e.g. 3 attempts). Every file load validates the expected keys exist
  before use (no bare `dict[key]` access on agent-to-agent JSON). On
  unrecoverable failure, the agent logs the reason and stops the pipeline
  rather than continuing on partial/guessed data.

---

## 1. Agent 1: Market Intelligence & Portfolio Architect
* **Assigned Model:** `claude-sonnet-5`
* **Tools:** `web_search` (with citations), `web_fetch` for specific pages found
  by search.
* **Determinism:** steer via prompt for precision/low creativity (see parameter
  note above).
* **Input:** Company name and main web page URL.
* **Core Objective:** Search public web data (company site, spec sheets, press
  releases, published datasheets) to map the company's material portfolio into
  distinguishable functional domains (e.g., Wear-Resistant, High-Strength
  Structural, Tool Steels). Every extracted fact must carry a source URL.
* **Deliverable:** `agent_1_baseline.json`

```jsonc
{
  "company": "string",
  "domains": [
    {
      "domain_name": "string",              // e.g. "Wear-Resistant"
      "grades": ["string"],                 // e.g. ["Wear-Resistant 400"]
      "manufacturing_constraints": {         // generic element/parameter limits
        "Mn": {"max": 1.6, "unit": "wt%"}
      }
    }
  ],
  "sources": [{"title": "string", "url": "string"}]
}
```

---

## 🛑 Human-in-the-Loop Checkpoint 1: Domain Selection
* **Action:** The human operator reviews Agent 1's domain breakdown and selects
  **one specific steel domain** to drive Agent 2.

---

## 2. Agent 2: Frontier Research & Mechanism Hunter
* **Assigned Model:** `claude-opus-5-5` (escalate to `claude-fable-5-1` for the
  most demanding literature-synthesis cases, per Anthropic's own guidance to
  reach for Fable when Opus falls short on deep, long-horizon reasoning).
* **Tools:** `web_search` (with citations) — **required**, not optional. Every
  `breakthrough_findings` entry must cite at least one source; reject/flag
  findings with no source before they reach Agent X.
* **Determinism:** steer via prompt for balanced exploratory reasoning.
* **Input:** The specific steel domain selected in Checkpoint 1.
* **Core Objective:** Search literature/patents for cutting-edge mechanisms,
  extracting chemical composition ranges, microstructural phases, processing
  routes, and their correlation with mechanical properties.
* **Deliverable:** `agent_2_report.json`

```jsonc
{
  "domain": "string",
  "breakthrough_findings": [
    {
      "mechanism": "string",
      "performance_correlation": "positive | negative | neutral",
      "optimizing_variable": "string",         // e.g. "Mn"
      "chemical_composition_range": {
        "C": {"min": 0.15, "max": 0.25},
        "Mn": {"min": 1.2, "max": 1.8}
      },
      "reported_mechanical_properties": {"...": "..."},
      "sources": [{"title": "string", "url": "string"}]   // required, >=1
    }
  ]
}
```

---

## 3. Agent X: Thermodynamic Simulator & Extrapolating Designer
* **Assigned Model:** none required for the numeric core (see note). If used to
  narrate a hypothesis in prose, `claude-sonnet-5`, steered via prompt for
  deterministic, literal output.
* **Note on "simulation":** the reference implementation ships with a
  transparent **heuristic extrapolation mode** (linear, flagged as such in its
  output) because no CALPHAD/TC-Python engine is wired in yet. Do not present
  its output to Agent 3 or to humans as a validated thermodynamic simulation
  until a real engine (Thermo-Calc TC-Python, or the open-source `pycalphad`)
  is integrated behind the same interface.
* **Input:** `agent_2_report.json` **and** `agent_1_baseline.json` (the
  extrapolation must be checked against the company's own manufacturing
  constraints — v1 only took Agent 2's report, which is how an out-of-spec
  recipe could slip through unnoticed).
* **Core Objective:** Isolate positive-correlation trends, extrapolate beyond
  literature bounds, and flag whether each extrapolated value is within or
  outside the company's stated manufacturing limits.
* **Deliverable:** `agent_x_simulation_results.json`

```jsonc
{
  "virtual_prototype": "string",
  "simulation_mode": "heuristic_linear_extrapolation | calphad",
  "extrapolated_parameters": [
    {
      "target_mechanism": "string",
      "base_variable": "string",
      "literature_tested_max": 0.0,
      "extrapolated_target_value": 0.0,
      "manufacturing_constraint_check": {
        "limit": 0.0,
        "unit": "string",
        "status": "within_limit | exceeds_limit | no_constraint_found"
      },
      "hypothesis": "string"
    }
  ],
  "simulated_phase_fraction": {"...": "..."},
  "required_cooling_rate_c_s": 0.0,
  "confidence_note": "string"   // e.g. "linear extrapolation, unvalidated by CALPHAD"
}
```

---

## 🔎 Agent V (new): Independent Constraint Validator
* **Assigned Model:** `claude-haiku-4-5-20251001` (a cheap, fast check — this is
  a structured verification pass, not open-ended reasoning), or pure code if
  the checks stay simple.
* **Role:** Reviews Agent X's output **without having produced it**, re-checks
  every `manufacturing_constraint_check` against `agent_1_baseline.json`
  directly, and flags any contradiction Agent X may have missed (mirrors the
  general good practice of having high-stakes technical output checked by a
  party that didn't produce it).
* **Input:** `agent_1_baseline.json` + `agent_x_simulation_results.json`.
* **Behavior:** if any parameter is flagged `exceeds_limit`, or a constraint
  cannot be found for a variable Agent X touched, the pipeline **halts and
  surfaces this to the human operator** before Agent 3 runs. The human can
  approve proceeding anyway (e.g., because the limit is about to be revised),
  reject the finding, or send it back to Agent X.
* **Deliverable:** `agent_v_validation.json` — a list of findings with
  `status: confirmed_within_limit | contradiction_found`, appended to the
  pipeline log either way.

---

## 4. Agent 3: Strategic Gap Analysis & TRIZ Problem Solver
* **Assigned Model:** `claude-opus-5-5`
* **Determinism:** steer via prompt for moderate creativity / cross-domain
  reasoning (see parameter note above).
* **Input:** `agent_1_baseline.json` + `agent_x_simulation_results.json` +
  `agent_v_validation.json`. Any `contradiction_found` entries must be
  explicitly addressed in the roadmap (e.g., "this recipe requires raising the
  Mn ceiling — flagged for review") rather than silently built upon.
* **Core Objective:** Compare current capabilities against the (validated)
  simulated materials, resolve trade-offs via TRIZ/first principles.
* **Deliverable:** **both** of the following (v1 only produced the Markdown,
  which is fragile for Agent 4 to parse back out):
  * `agent_3_roadmap.md` — human-readable narrative.
  * `agent_3_roadmap.json` — structured form for Agent 4:
    ```jsonc
    {
      "gaps": [{"description": "string", "contradiction": "string", "triz_principle": "string"}],
      "proposed_recipes": [{"grade_name": "string", "composition": {"...": "..."}, "source_extrapolation": "string"}],
      "roadmap_steps": [{"step": 1, "action": "string", "owner": "string", "est_duration": "string"}]
    }
    ```

---

## 🛑 Human-in-the-Loop Checkpoint 2: Roadmap Review
* **Action:** The human operator reviews Agent 3's roadmap and proposed
  recipes before they are sent to Agent 4 or committed to lab work / further
  spend. This checkpoint did not exist in v1; strategic and investment
  decisions should not flow straight from Agent 3 into Agent 4 unreviewed.

---

## 5. Agent 4: IP-Freedom & Life Cycle Assessment (LCA) Optimizer
* **Assigned Model:** `claude-sonnet-5`
* **Tools:** `web_search` for public patent/literature checks.
* **Determinism:** steer via prompt for rigid, factual auditing.
* **Input:** `agent_3_roadmap.json` (approved at Checkpoint 2).
* **Core Objective:** Screen Freedom-to-Operate (FTO) risk via public patent
  search and estimate CO2/energy footprints for the proposed manufacturing
  routes.
* **Scope limitation (important):** this agent produces a **preliminary
  screening**, not a legal FTO opinion. Its output must say so explicitly, and
  any recipe it flags as promising should be routed to a qualified patent
  attorney for a real freedom-to-operate opinion before commercial commitment.
* **Deliverable:** `agent_4_audit.md` + `agent_4_audit.json`
  (`{"fto_screen": [...], "lca_estimate": {...}, "requires_legal_review": [...]}`).

---

## Pipeline Summary

```
Agent 1  --(web_search)-->  agent_1_baseline.json
   |
   v  [Checkpoint 1: human picks domain]
   |
Agent 2  --(web_search)-->  agent_2_report.json
   |
   v
Agent X  (extrapolate + constraint-check against Agent 1) --> agent_x_simulation_results.json
   |
   v
Agent V  (independent re-check) --> agent_v_validation.json
   |
   v  [halt + human review if contradiction_found]
   |
Agent 3  (TRIZ / gap analysis) --> agent_3_roadmap.md + agent_3_roadmap.json
   |
   v  [Checkpoint 2: human reviews roadmap]
   |
Agent 4  (FTO screen + LCA, NOT a legal opinion) --> agent_4_audit.md + agent_4_audit.json
```
