"""
Pipeline Report Builder

Consolidates the outputs of all six agents into one structured PDF: Agent 1
& 2 (market intelligence + frontier research), Agent X & V (simulation +
independent validation), Agent 3 (strategic roadmap), Agent 4 (IP/LCA
audit) -- in that order, as sections of a single document.

Deliberately tolerant of a partial pipeline run: any stage whose output
file doesn't exist yet is rendered as "not yet run" rather than raising, so
this can be used to check progress mid-pipeline, not just at the very end.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logging.basicConfig(level=logging.INFO, format="[Report] %(message)s")
logger = logging.getLogger("report_builder")

STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle(name="SectionTitle", parent=STYLES["Heading1"], spaceBefore=18))
STYLES.add(ParagraphStyle(name="Note", parent=STYLES["Normal"], textColor=colors.grey, italic=True))
CELL_STYLE = ParagraphStyle(name="Cell", parent=STYLES["Normal"], fontSize=8, leading=10)


# ------------------------------------------------------------------ loading


def _load_json_optional(path: str) -> Optional[Dict[str, Any]]:
  if not os.path.exists(path):
    return None
  with open(path, "r", encoding="utf-8") as f:
    return json.load(f)


def _load_text_optional(path: str) -> Optional[str]:
  if not os.path.exists(path):
    return None
  with open(path, "r", encoding="utf-8") as f:
    return f.read()


# ---------------------------------------------------------------- rendering


def _not_run(label: str) -> List[Any]:
  return [Paragraph(f"{label} has not been run yet.", STYLES["Note"]), Spacer(1, 12)]


def _cell(value: Any) -> Paragraph:
  """Wrap a table cell's text in a Paragraph so it word-wraps instead of
  overflowing -- plain strings in reportlab Table cells don't wrap."""
  if value is None:
    text = "--"
  elif isinstance(value, (list, tuple)):
    # e.g. optimizing_variable can be a single name or a list of names --
    # render "Mn, retained_austenite" instead of Python's "['Mn', ...]" repr.
    text = ", ".join(str(v) for v in value)
  else:
    text = str(value)
  return Paragraph(escape(text), CELL_STYLE)


def _format_properties(properties: Optional[Any]) -> str:
  """Render an open-ended {property_name: {value, unit}} dict as one
  compact string -- there's no fixed set of properties to lay out as
  columns, since what's actually reported varies per grade/finding.

  Defensive against malformed input (e.g. a list where a dict was expected)
  the same way the rest of this file is about agent output that doesn't
  match its schema -- report_builder's whole job is to not crash on it.
  """
  if not properties or not isinstance(properties, dict):
    return "--"
  parts = []
  for name, entry in properties.items():
    if isinstance(entry, dict):
      value, unit = entry.get("value"), entry.get("unit") or ""
      parts.append(f"{name}: {value} {unit}".strip())
    else:
      parts.append(f"{name}: {entry}")
  return "; ".join(parts)


def _table(headers: List[str], rows: List[List[Any]], col_widths: Optional[List[float]] = None) -> Table:
  data = [[_cell(h) for h in headers]] + [[_cell(v) for v in row] for row in rows]
  table = Table(data, colWidths=col_widths, repeatRows=1)
  table.setStyle(TableStyle([
      ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3b45")),
      ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
      ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
      ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
      ("VALIGN", (0, 0), (-1, -1), "TOP"),
      ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
  ]))
  return table


def _markdown_lite(markdown_text: str) -> List[Any]:
  """Minimal markdown -> flowables: headings, bullets, paragraphs. Not a
  full CommonMark renderer -- enough for the narrative Agent 3/4 produce."""
  flowables: List[Any] = []
  heading_styles = {1: "Heading2", 2: "Heading3", 3: "Heading4"}
  for raw_line in markdown_text.splitlines():
    line = raw_line.rstrip()
    if not line:
      flowables.append(Spacer(1, 6))
      continue
    heading = re.match(r"^(#{1,6})\s+(.*)", line)
    if heading:
      level = min(len(heading.group(1)), 3)
      flowables.append(Paragraph(escape(heading.group(2)), STYLES[heading_styles[level]]))
      continue
    bullet = re.match(r"^[-*]\s+(.*)", line)
    if bullet:
      flowables.append(Paragraph(f"&bull;&nbsp;&nbsp;{escape(bullet.group(1))}", STYLES["Normal"]))
      continue
    flowables.append(Paragraph(escape(line), STYLES["Normal"]))
  return flowables


# ------------------------------------------------------------------ sections


def _section_1(agent_1: Optional[Dict[str, Any]], agent_2: Optional[Dict[str, Any]]) -> List[Any]:
  story: List[Any] = [Paragraph("1. Market Intelligence &amp; Frontier Research (Agents 1 &amp; 2)", STYLES["SectionTitle"])]

  if agent_1 is None:
    story += _not_run("Agent 1")
  else:
    story.append(Paragraph(f"Company: {escape(agent_1.get('company') or '--')}", STYLES["Normal"]))
    domains = agent_1.get("domains", [])
    story.append(Paragraph(f"Domains mapped: {', '.join(d.get('domain_name', '?') for d in domains)}", STYLES["Normal"]))
    story.append(Spacer(1, 8))

    # Agent 2 is scoped to one domain; show that domain's grades in detail.
    selected_name = agent_2.get("domain") if agent_2 else None
    selected_domain = next((d for d in domains if d.get("domain_name") == selected_name), domains[0] if domains else None)

    if selected_domain:
      story.append(Paragraph(f"Domain detail: {escape(selected_domain.get('domain_name', '?'))}", STYLES["Heading2"]))
      story.append(Paragraph(escape(selected_domain.get("domain_description") or ""), STYLES["Normal"]))
      pm = selected_domain.get("includes_powder_metallurgy")
      story.append(Paragraph(f"Includes powder metallurgy grades: {pm if pm is not None else 'unknown'}", STYLES["Normal"]))
      story.append(Spacer(1, 6))

      rows = []
      for g in selected_domain.get("grades", []):
        if not isinstance(g, dict):
          # Legacy/malformed data (e.g. a bare grade-name string instead of
          # a full record) -- show the name, skip the detail columns rather
          # than crash the whole report over one bad entry.
          rows.append([g, "--", "--", "--"])
          continue
        rows.append([
            g.get("grade_name"),
            g.get("is_powder_metallurgy"),
            _format_properties(g.get("mechanical_properties")),
            ", ".join(g.get("manufacturing_methods") or []) or "--",
        ])
      if rows:
        # mechanical_properties is open-ended (whatever Agent 1 actually
        # found per grade, not a fixed set of columns decided in advance),
        # so it gets one flexible joined-text column rather than a fixed
        # Yield/Tensile/Hardness column each.
        story.append(_table(
            ["Grade", "PM?", "Mechanical Properties (as found)", "Manufacturing"],
            rows,
            col_widths=[1.1 * inch, 0.5 * inch, 2.5 * inch, 1.6 * inch],
        ))
      story.append(Spacer(1, 12))

  if agent_2 is None:
    story += _not_run("Agent 2")
  else:
    story.append(Paragraph("Performance priorities", STYLES["Heading2"]))
    pri_rows = [[p.get("property"), p.get("direction"), p.get("rationale")] for p in agent_2.get("performance_priorities", [])]
    if pri_rows:
      story.append(_table(["Property", "Direction", "Rationale"], pri_rows, col_widths=[1.2 * inch, 0.9 * inch, 3.9 * inch]))
    story.append(Spacer(1, 8))

    topics = agent_2.get("research_topics_investigated", [])
    story.append(Paragraph(f"Research topics investigated ({len(topics)}): {', '.join(topics)}", STYLES["Normal"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Breakthrough findings", STYLES["Heading2"]))
    find_rows = [
        [f.get("mechanism"), f.get("performance_correlation"), f.get("optimizing_variable"),
         f.get("research_topic"), len(f.get("sources") or [])]
        for f in agent_2.get("breakthrough_findings", [])
    ]
    if find_rows:
      story.append(_table(
          ["Mechanism", "Correlation", "Variable", "Topic", "#Sources"],
          find_rows,
          col_widths=[2.2 * inch, 0.8 * inch, 0.9 * inch, 1.4 * inch, 0.7 * inch],
      ))
    story.append(Spacer(1, 8))

    materials = agent_2.get("materials_found", [])
    if materials:
      story.append(Paragraph("Comparator materials found in literature", STYLES["Heading2"]))
      mat_rows = [
          [m.get("material_name"), _format_properties(m.get("mechanical_properties")),
           m.get("research_topic"), len(m.get("sources") or [])]
          for m in materials
      ]
      story.append(_table(
          ["Material", "Mechanical Properties (as found)", "Topic", "#Sources"],
          mat_rows,
          col_widths=[1.4 * inch, 2.6 * inch, 1.4 * inch, 0.6 * inch],
      ))
    story.append(Spacer(1, 12))

  return story


def _section_2(agent_x: Optional[Dict[str, Any]], agent_v: Optional[Dict[str, Any]]) -> List[Any]:
  story: List[Any] = [Paragraph("2. Simulation &amp; Validation (Agents X &amp; V)", STYLES["SectionTitle"])]

  if agent_x is None:
    story += _not_run("Agent X")
  else:
    story.append(Paragraph(
        f"Domain: {escape(agent_x.get('domain', '?'))} | "
        f"Simulation mode: {escape(agent_x.get('simulation_mode', '?'))} | "
        f"Requires human review: {agent_x.get('requires_human_review')}",
        STYLES["Normal"],
    ))
    story.append(Spacer(1, 6))
    rows = [
        [p.get("base_variable"), p.get("variable_category"), p.get("literature_tested_max"),
         p.get("extrapolated_target_value"), (p.get("manufacturing_constraint_check") or {}).get("status"),
         _format_properties(p.get("literature_reported_properties"))]
        for p in agent_x.get("extrapolated_parameters", [])
    ]
    if rows:
      # "Reported Context" is the literature's actual measured property at
      # the tested condition (e.g. impact toughness at that composition) --
      # grounding evidence behind the hypothesis, not itself extrapolated.
      story.append(_table(
          ["Variable", "Category", "Lit. Max", "Extrapolated", "Constraint Status", "Reported Context"],
          rows,
          col_widths=[1.0 * inch, 0.8 * inch, 0.6 * inch, 0.8 * inch, 1.1 * inch, 1.7 * inch],
      ))
    story.append(Paragraph(escape(agent_x.get("confidence_note") or ""), STYLES["Note"]))
    story.append(Spacer(1, 12))

  if agent_v is None:
    story += _not_run("Agent V")
  else:
    story.append(Paragraph(f"Requires human review: {agent_v.get('requires_human_review')}", STYLES["Normal"]))
    story.append(Spacer(1, 6))
    rows = [
        [f.get("variable"), f.get("variable_category"), f.get("claimed_status"),
         f.get("recomputed_status"), f.get("status")]
        for f in agent_v.get("findings", [])
    ]
    if rows:
      story.append(_table(
          ["Variable", "Category", "Agent X Claimed", "Independently Recomputed", "Status"],
          rows,
          col_widths=[1.2 * inch, 1.0 * inch, 1.3 * inch, 1.5 * inch, 1.0 * inch],
      ))
    story.append(Spacer(1, 12))

  return story


def _section_3(agent_3_json: Optional[Dict[str, Any]], agent_3_md: Optional[str]) -> List[Any]:
  story: List[Any] = [Paragraph("3. Strategic Roadmap (Agent 3)", STYLES["SectionTitle"])]

  if agent_3_json is None and agent_3_md is None:
    return story + _not_run("Agent 3")

  if agent_3_md:
    story += _markdown_lite(agent_3_md)
    story.append(Spacer(1, 12))

  if agent_3_json:
    story.append(Paragraph("Gaps", STYLES["Heading2"]))
    rows = [[g.get("description"), g.get("contradiction"), g.get("triz_principle")] for g in agent_3_json.get("gaps", [])]
    if rows:
      story.append(_table(["Description", "Contradiction", "TRIZ Principle"], rows, col_widths=[2.2 * inch, 2.2 * inch, 1.6 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Proposed recipes", STYLES["Heading2"]))
    rows = [
        [r.get("grade_name"), ", ".join(f"{k}: {v}" for k, v in (r.get("composition") or {}).items()), r.get("source_extrapolation")]
        for r in agent_3_json.get("proposed_recipes", [])
    ]
    if rows:
      story.append(_table(["Grade", "Composition", "Source Extrapolation"], rows, col_widths=[1.3 * inch, 2.7 * inch, 2.0 * inch]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Roadmap steps", STYLES["Heading2"]))
    rows = [[s.get("step"), s.get("action"), s.get("owner"), s.get("est_duration")] for s in agent_3_json.get("roadmap_steps", [])]
    if rows:
      story.append(_table(["Step", "Action", "Owner", "Est. Duration"], rows, col_widths=[0.5 * inch, 3.2 * inch, 1.3 * inch, 1.0 * inch]))
    story.append(Spacer(1, 12))

  return story


def _section_4(agent_4: Optional[Dict[str, Any]]) -> List[Any]:
  story: List[Any] = [Paragraph("4. IP-Freedom &amp; LCA Audit (Agent 4)", STYLES["SectionTitle"])]

  if agent_4 is None:
    return story + _not_run("Agent 4")

  story.append(Paragraph(escape(agent_4.get("scope_note", "")), STYLES["Note"]))
  story.append(Spacer(1, 8))

  story.append(Paragraph("Freedom-to-Operate screen", STYLES["Heading2"]))
  rows = [
      [e.get("grade_name"), e.get("risk_note"), len(e.get("public_patent_hits") or [])]
      for e in agent_4.get("fto_screen", [])
  ]
  if rows:
    story.append(_table(["Grade", "Risk Note", "#Patent Hits"], rows, col_widths=[1.3 * inch, 3.9 * inch, 0.8 * inch]))
  story.append(Spacer(1, 8))

  story.append(Paragraph("LCA estimate", STYLES["Heading2"]))
  rows = [
      [grade, est.get("co2_kg_per_tonne_estimate"), est.get("energy_mj_per_tonne_estimate"), est.get("basis")]
      for grade, est in (agent_4.get("lca_estimate") or {}).items()
  ]
  if rows:
    story.append(_table(["Grade", "CO2 (kg/t)", "Energy (MJ/t)", "Basis"], rows, col_widths=[1.3 * inch, 1.0 * inch, 1.1 * inch, 2.6 * inch]))
  story.append(Spacer(1, 8))

  review = agent_4.get("requires_legal_review", [])
  story.append(Paragraph(f"Requires legal review: {', '.join(review) if review else 'none flagged'}", STYLES["Normal"]))

  return story


# -------------------------------------------------------------------- build


def build_report(data_dir: str = "temp_data", output_path: str = "pipeline_report.pdf") -> str:
  """Reads whatever stage output files exist in `data_dir` and writes one
  consolidated PDF to `output_path`. Stages that haven't run yet are
  rendered as "not yet run" rather than raising."""

  def p(name: str) -> str:
    return os.path.join(data_dir, name)

  agent_1 = _load_json_optional(p("agent_1_baseline.json"))
  agent_2 = _load_json_optional(p("agent_2_report.json"))
  agent_x = _load_json_optional(p("agent_x_simulation_results.json"))
  agent_v = _load_json_optional(p("agent_v_validation.json"))
  agent_3_json = _load_json_optional(p("agent_3_roadmap.json"))
  agent_3_md = _load_text_optional(p("agent_3_roadmap.md"))
  agent_4 = _load_json_optional(p("agent_4_audit.json"))

  doc = SimpleDocTemplate(output_path, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
  story: List[Any] = [
      Paragraph("Steel R&amp;D Pipeline Report", STYLES["Title"]),
      Paragraph(escape(agent_1.get("company") or "Unknown") if agent_1 else "Company: not yet known", STYLES["Normal"]),
      Spacer(1, 12),
  ]
  story += _section_1(agent_1, agent_2)
  story.append(PageBreak())
  story += _section_2(agent_x, agent_v)
  story.append(PageBreak())
  story += _section_3(agent_3_json, agent_3_md)
  story.append(PageBreak())
  story += _section_4(agent_4)

  doc.build(story)
  logger.info("Wrote consolidated report to '%s'.", output_path)
  return output_path


if __name__ == "__main__":
  build_report()
