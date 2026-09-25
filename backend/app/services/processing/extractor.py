"""Rule-based field extraction (Phase 3).

Ported from the notebook's ``extract_reason`` / ``extract_year``. Heuristic and
deterministic (not ML): reason = first sentence of the description (HTML
stripped, length-capped); year = first 20YY in the title, else the publication
year, else empty.
"""
from __future__ import annotations

import re
from typing import Optional

from app.services.processing.normalizer import normalize_datetime

_TAG_RE = re.compile(r"<.*?>")
_SENT_SPLIT = re.compile(r"(?<=[.!?]) +")
_YEAR_RE = re.compile(r"20\d{2}")


def extract_reason(description: Optional[str], limit: int = 250) -> str:
    if not description:
        return ""
    text = _TAG_RE.sub("", description).replace("\n", " ").strip()
    if not text:
        return ""
    sentences = _SENT_SPLIT.split(text)
    first = sentences[0] if sentences else text
    return first[:limit].strip()


def extract_year(title: Optional[str], published_at: Optional[str]) -> str:
    years = _YEAR_RE.findall(title or "")
    if years:
        return years[0]
    dt = normalize_datetime(published_at)
    if dt is not None:
        return str(dt.year)
    return ""
