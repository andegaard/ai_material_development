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

- `agent_x_simulator.py` — implemented (Agent X: thermodynamic
  extrapolation + manufacturing-constraint checking).
- Agents 1, 2, V, 3, 4 and the orchestrator — specified in
  `agent_instructions.md` but not yet implemented in code.

## Layout

- `agent_instructions.md` — current (v2) pipeline specification.
- `agent_x_simulator.py` — current (v2) Agent X implementation.
- `archive/v1_prototype/` — earlier prototype (v1), kept for reference. Uses
  retired model IDs and deprecated temperature parameters; superseded by the
  v2 spec above.
