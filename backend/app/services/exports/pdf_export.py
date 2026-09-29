"""PDF export (.pdf) using ReportLab.

Landscape A4 document with: a title, the search parameters, category/state
summary tables, and a full (wrapping) article table. Counts shown are computed
from the *actual* rows passed in - nothing is fabricated.
"""
from __future__ import annotations

import html
import io
import re
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.exports.common import (
    EXPORT_COLUMNS,
    HEADERS,
    cell,
    search_parameter_rows,
    summarize,
)

# Narrow columns get more width; Title/Link get the most.
_COL_WIDTHS = {
    "title": 46 * mm,
    "url": 34 * mm,
    "reason": 30 * mm,
}
_DEFAULT_WIDTH = 16 * mm

# Per-column render caps. Google News URLs are very long unbroken tokens;
# ReportLab splits over-long words character-by-character, producing rows
# taller than the page frame (LayoutError => HTTP 500 on big exports).
# Truncating display text keeps every row page-sized without touching the
# underlying data (CSV/XLSX/DOCX still carry the full values).
_MAX_CELL_CHARS = {
    "title": 160,
    "reason": 120,
    "url": 70,
}
_DEFAULT_MAX_CHARS = 60
_TAG_RE = re.compile(r"<[^>]*>")


def _pdf_cell_text(row: dict, key: str) -> str:
    text = _TAG_RE.sub(" ", cell(row, key))
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    # Escape markup so Paragraph never mis-parses publisher text.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    limit = _MAX_CELL_CHARS.get(key, _DEFAULT_MAX_CHARS)
    if len(text) > limit:
        text = text[: limit - 1] + "\u2026"
    return text or "\u2014"


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fb")]),
        ]
    )


def _simple_table(title: str, header: str, pairs: List) -> List:
    flow = [Paragraph(title, _styles()["Heading3"]), Spacer(1, 2 * mm)]
    data = [[header, "Count"]] + [[str(k), str(v)] for k, v in pairs]
    table = Table(data, colWidths=[70 * mm, 20 * mm], repeatRows=1)
    table.setStyle(_table_style())
    flow.append(table)
    flow.append(Spacer(1, 5 * mm))
    return flow


_STYLES = None


def _styles():
    global _STYLES
    if _STYLES is None:
        _STYLES = getSampleStyleSheet()
    return _STYLES


def build_pdf(rows: List[dict], meta: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=str(meta.get("query", "NewsLens export")),
    )

    styles = _styles()
    flow = [Paragraph("NewsLens - Search Export", styles["Title"]), Spacer(1, 4 * mm)]

    # Search parameters
    flow.append(Paragraph("Search Parameters", styles["Heading2"]))
    flow.append(Spacer(1, 2 * mm))
    param_data = [[k, str(v)] for k, v in search_parameter_rows(meta)]
    param_table = Table(param_data, colWidths=[40 * mm, 120 * mm])
    param_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    flow.append(param_table)
    flow.append(Spacer(1, 6 * mm))

    # Summaries
    flow.append(Paragraph("Summaries", styles["Heading2"]))
    flow.append(Spacer(1, 2 * mm))
    flow += _simple_table("By Category", "Category", summarize(rows, "category"))
    flow += _simple_table("By State", "State", summarize(rows, "state"))
    flow += _simple_table("By Provider", "Provider", summarize(rows, "provider"))

    # Article table
    flow.append(Paragraph(f"Articles ({len(rows)})", styles["Heading2"]))
    flow.append(Spacer(1, 2 * mm))
    body = [HEADERS]
    for r in rows:
        body.append(
            [
                Paragraph(_pdf_cell_text(r, key), styles["BodyText"])
                for _, key in EXPORT_COLUMNS
            ]
        )
    widths = [_COL_WIDTHS.get(key, _DEFAULT_WIDTH) for _, key in EXPORT_COLUMNS]
    # LongTable streams rows across pages instead of demanding one giant frame.
    article_table = LongTable(body, colWidths=widths, repeatRows=1)
    article_table.setStyle(_table_style())
    flow.append(article_table)

    if not rows:
        flow.append(Spacer(1, 3 * mm))
        flow.append(Paragraph("No articles matched this search.", styles["BodyText"]))

    doc.build(flow)
    return buf.getvalue()
