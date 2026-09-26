"""Shared column definitions and summary helpers for all exporters.

The column set mirrors the notebook's original export so results stay
recognisable. Every exporter consumes a list of *serialized* article dicts
(the shape produced by ``app.services.article_repo.serialize``) plus a small
``meta`` dict describing the search that produced them. No values are invented
here - missing fields render as blank/"Unknown" exactly as stored.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

# (display header, row-dict key)
EXPORT_COLUMNS: List[Tuple[str, str]] = [
    ("Title", "title"),
    ("Source", "source"),
    ("Provider", "provider"),
    ("Name of Exam", "name_of_exam"),
    ("Exam Category", "exam_category"),
    ("Board", "board"),
    ("State", "state"),
    ("Conducted In", "conducted_in"),
    ("Conducted By", "conducted_by"),
    ("Category", "category"),
    ("Reason", "reason"),
    ("PBT/CBT", "pbt_cbt"),
    ("Exam Year", "exam_year"),
    ("Matched Keyword", "keyword_matched"),
    ("Published Date", "published_date"),
    ("Link", "url"),
]

HEADERS = [h for h, _ in EXPORT_COLUMNS]
KEYS = [k for _, k in EXPORT_COLUMNS]

# Formats -> (media type, file extension). Used by the export route.
FORMAT_MEDIA_TYPES: Dict[str, Tuple[str, str]] = {
    "csv": ("text/csv", "csv"),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "pdf": ("application/pdf", "pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
}


def cell(row: dict, key: str) -> str:
    """Return a display-safe string for a field (never None)."""
    value = row.get(key)
    return "" if value is None else str(value)


def data_rows(rows: List[dict]) -> List[List[str]]:
    return [[cell(r, k) for k in KEYS] for r in rows]


def summarize(rows: List[dict], key: str) -> List[Tuple[str, int]]:
    """Count occurrences of a field, most frequent first."""
    counter = Counter((r.get(key) or "Unknown") for r in rows)
    return counter.most_common()


def search_parameter_rows(meta: dict) -> List[Tuple[str, str]]:
    return [
        ("Search Query", str(meta.get("query", ""))),
        ("Date Range", f"{meta.get('from_date') or '-'} to {meta.get('to_date') or '-'}"),
        ("Sources", ", ".join(meta.get("sources", []) or [])),
        ("Country", str(meta.get("country", ""))),
        ("Language", str(meta.get("language", ""))),
        ("Total Articles", str(meta.get("total", ""))),
        ("Generated At", str(meta.get("generated_at", ""))),
    ]
