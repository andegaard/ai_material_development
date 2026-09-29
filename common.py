"""
Shared helpers for the multi-agent steel R&D pipeline.

Implements the cross-cutting policies from agent_instructions.md so each
agent doesn't reimplement them slightly differently:
  - every LLM call is wrapped in retry-with-backoff (3 attempts)
  - every agent-to-agent JSON file is checked for required keys before use,
    and before being written
  - findings with no cited source are dropped, not passed downstream
  - unrecoverable failure halts the pipeline (`PipelineHalt`) rather than
    continuing on partial/guessed data
"""

import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("common")

T = TypeVar("T")


class PipelineHalt(Exception):
  """Raised to stop the pipeline on unrecoverable failure or a
  human-rejected checkpoint. The orchestrator catches this at the top
  level; individual agents let it propagate rather than continuing on
  bad data."""


# ------------------------------------------------------------- JSON I/O


def require_keys(data: Dict[str, Any], required_keys: List[str], *, context: str = "") -> None:
  missing = [k for k in required_keys if k not in data]
  if missing:
    where = f" in {context}" if context else ""
    raise PipelineHalt(f"Missing required key(s){where}: {missing}")


def load_json_validated(path: str, required_keys: Optional[List[str]] = None) -> Dict[str, Any]:
  try:
    with open(path, "r", encoding="utf-8") as f:
      data = json.load(f)
  except FileNotFoundError as exc:
    raise PipelineHalt(
        f"Required input file not found: '{path}'. Check that the upstream "
        "agent ran and wrote its output here."
    ) from exc
  except json.JSONDecodeError as exc:
    raise PipelineHalt(f"'{path}' is not valid JSON: {exc}") from exc

  if required_keys:
    require_keys(data, required_keys, context=f"'{path}'")
  return data


def save_json_validated(
    data: Dict[str, Any], path: str, required_keys: Optional[List[str]] = None
) -> None:
  """Validate `data` has the required top-level keys, then write it.

  Mirrors the "validate each JSON output against its schema before writing
  it to disk; on validation failure, halt the pipeline" policy.
  """
  if required_keys:
    require_keys(data, required_keys, context=f"output for '{path}'")
  with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
  logger.info("Wrote '%s'.", path)


# ------------------------------------------------------------- LLM calls


def call_with_retry(
    fn: Callable[[], T], *, attempts: int = 3, base_delay_s: float = 2.0, label: str = "LLM call"
) -> T:
  """Call `fn` with exponential backoff, per the pipeline's error-handling
  policy. Raises `PipelineHalt` (not the original exception) once attempts
  are exhausted, so callers only need to handle one failure type."""
  last_exc: Optional[Exception] = None
  for attempt in range(1, attempts + 1):
    try:
      return fn()
    except Exception as exc:  # noqa: BLE001 - deliberate retry boundary
      last_exc = exc
      logger.warning("%s failed (attempt %d/%d): %s", label, attempt, attempts, exc)
      if attempt < attempts:
        time.sleep(base_delay_s * (2 ** (attempt - 1)))
  raise PipelineHalt(f"{label} failed after {attempts} attempts: {last_exc}") from last_exc


def get_anthropic_client():
  from anthropic import Anthropic

  api_key = os.environ.get("ANTHROPIC_API_KEY")
  if not api_key:
    raise PipelineHalt(
        "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
    )
  return Anthropic(api_key=api_key)


# NOTE -- VERIFY BEFORE RUNNING: these are the hosted server-tool type
# strings as of this writing. Confirm them against the current Anthropic API
# docs before the pipeline actually runs; server-tool type versions
# (the "_YYYYMMDD" suffix) do change between API releases.
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}
WEB_FETCH_TOOL = {"type": "web_fetch_20250910", "name": "web_fetch"}


def extract_text(response: Any) -> str:
  """Concatenate every text block in a Messages API response, skipping
  tool_use / server_tool_use / tool_result blocks."""
  return "".join(
      block.text for block in response.content if getattr(block, "type", None) == "text"
  )


def extract_json_object(text: str) -> Dict[str, Any]:
  """Pull a JSON object out of model output that may be wrapped in prose or
  a ```json fence -- agents are prompted to emit exactly one such object."""
  fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
  candidate = fence_match.group(1) if fence_match else text
  try:
    return json.loads(candidate)
  except json.JSONDecodeError:
    pass

  start, end = candidate.find("{"), candidate.rfind("}")
  if start == -1 or end == -1 or end <= start:
    raise PipelineHalt(f"Could not find a JSON object in model output: {text[:500]!r}")
  return json.loads(candidate[start : end + 1])


# ------------------------------------------------------- domain policies


def require_sources(entries: List[Dict[str, Any]], *, entry_label: str = "entry") -> List[Dict[str, Any]]:
  """Drop entries with no `sources`, per the "reject/flag findings with no
  source before they reach downstream agents" policy."""
  kept = []
  for entry in entries:
    if not entry.get("sources"):
      logger.warning(
          "Dropping %s with no source: %r", entry_label, entry.get("mechanism") or entry
      )
      continue
    kept.append(entry)
  return kept


LEGACY_CONSTRAINT_KEY_MAP = {
    "max_manganese_limit": "Mn",
    "max_carbon_limit": "C",
    "max_silicon_limit": "Si",
    "max_chromium_limit": "Cr",
}


def extract_manufacturing_constraints(
    baseline: Dict[str, Any], domain_name: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
  """Pull element -> {max, unit} constraints out of an Agent 1 baseline file.

  Supports both the v2 `manufacturing_constraints` schema (nested under each
  domain) and legacy flat keys like `max_manganese_limit`. Shared by Agent X
  (to extrapolate against) and Agent V (to independently re-check Agent X's
  work) so both always read the same constraints from the same place.

  `domain_name`, when given, restricts this to that one domain's constraints
  instead of merging every domain in the baseline together. Agent 2/X/V all
  operate on one human-selected domain at a time; without this, two domains
  with different limits for the same element would silently overwrite each
  other (whichever comes later in the list wins) and Agent X could end up
  checking an extrapolated value against the wrong domain's limit.
  """
  constraints: Dict[str, Dict[str, Any]] = {}

  domains = baseline.get("domains", [])
  if domain_name is not None:
    domains = [d for d in domains if d.get("domain_name") == domain_name]
    if not domains:
      logger.warning(
          "No domain named '%s' found in baseline; no manufacturing "
          "constraints will be applied.", domain_name,
      )

  for domain in domains:
    for element, limit in domain.get("manufacturing_constraints", {}).items():
      if isinstance(limit, dict) and "max" in limit:
        constraints[element] = {"max": limit["max"], "unit": limit.get("unit", "wt%")}

  # Legacy flat schema has no notion of domains, so it's applied regardless
  # of domain_name -- it predates the v2 per-domain schema entirely.
  for key, element in LEGACY_CONSTRAINT_KEY_MAP.items():
    if key in baseline and element not in constraints:
      constraints[element] = {"max": baseline[key], "unit": "wt%"}

  return constraints
