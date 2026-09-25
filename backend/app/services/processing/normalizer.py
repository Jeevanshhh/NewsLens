"""Normalization helpers (Phase 3).

Cleans text fields and coerces heterogeneous provider timestamps into a
single canonical, timezone-aware ISO-8601 (UTC) representation. Malformed
dates are handled safely (returned as ``None``) - records are never dropped
and the raw value is always preserved upstream.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as dtparser

from app.schemas.article import Article

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<.*?>")


def strip_html(text: Optional[str]) -> str:
    # Remove any markup tags, then decode HTML entities (e.g. ``&nbsp;``,
    # ``&amp;``, ``&#39;``) so stored/exported text is clean and readable.
    return html.unescape(_TAG_RE.sub("", text or ""))


def normalize_whitespace(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    collapsed = _WS_RE.sub(" ", text).strip()
    return collapsed or None


def normalize_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse a provider date string into an aware UTC datetime, or None."""
    if not raw or not str(raw).strip():
        return None
    try:
        dt = dtparser.parse(str(raw))
    except (ValueError, OverflowError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def normalize_article(article: Article) -> Article:
    """Return a cleaned copy of an article (does not mutate the input)."""
    return article.model_copy(
        update={
            "title": (normalize_whitespace(strip_html(article.title)) or "").strip(),
            "description": normalize_whitespace(strip_html(article.description)),
            "url": (article.url or "").strip(),
            "source": normalize_whitespace(article.source),
            "author": normalize_whitespace(article.author),
        }
    )
