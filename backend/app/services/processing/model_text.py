"""Single canonical model-text builder shared by TRAINING and INFERENCE.

Historically the topic model was trained on standalone synthetic headlines while
production fed ``f"{title} {description}"`` into ``predict_topic``. That train/
serve skew is the mismatch this module exists to remove: *one* function defines
``MODEL_TEXT`` for every caller.

Dependency-light on purpose (stdlib only) so both the offline ML scripts and the
FastAPI runtime import the exact same logic and cannot drift apart.

Transformation (deterministic, information-preserving - no truncation):
  1. Unicode NFKC normalisation (fold exotic spacing/compatibility forms).
  2. HTML tag strip + entity unescape.
  3. Whitespace collapse to single spaces, trim.
  4. Treat empty/blank description as absent (title-only, no trailing space).
  5. Join non-empty parts with a single space.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Optional

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]*>")


def normalize_text(value: Optional[str]) -> str:
    """NFKC-normalise, strip HTML, unescape entities and collapse whitespace."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = html.unescape(_TAG_RE.sub(" ", text))
    return _WS_RE.sub(" ", text).strip()


def build_model_text(title: Optional[str], description: Optional[str] = None) -> str:
    """Return the canonical model input for a news article.

    ``MODEL_TEXT = normalize(title) + " " + normalize(description)`` where a
    missing/blank description contributes nothing (no trailing separator).
    """
    parts = [normalize_text(title), normalize_text(description)]
    return " ".join(p for p in parts if p)


__all__ = ["normalize_text", "build_model_text"]
