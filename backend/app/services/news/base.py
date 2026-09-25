"""Shared helpers for news collectors.

Centralises the HTTP-with-timeout + defensive JSON parsing pattern and the
search parameters, so every provider handles failures the same way: log the
technical detail on the backend and return an empty result set rather than
raising, so one provider failing does not break a multi-source search.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from app.core.logging import get_logger

logger = get_logger("app.services.news")

DEFAULT_TIMEOUT = 15  # seconds


@dataclass
class SearchContext:
    """Normalized request parameters shared by all collectors."""

    query: str
    from_date: Optional[str] = None   # 'YYYY-MM-DD' (provider permitting)
    to_date: Optional[str] = None     # 'YYYY-MM-DD' (provider permitting)
    country: str = "in"
    language: str = "en"
    max_results: int = 10


def http_get_json(
    url: str,
    params: dict[str, Any],
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[dict]:
    """GET ``url`` and return parsed JSON, or ``None`` on any failure.

    Handles network/timeout errors, non-200 status and malformed bodies.
    Never re-raises, so a single provider outage degrades gracefully.
    """
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:  # timeouts, connection errors...
        logger.warning("Request to %s failed: %s", url, exc)
        return None

    if response.status_code != 200:
        logger.warning("Provider endpoint %s returned HTTP %s", url, response.status_code)
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("Provider endpoint %s returned a non-JSON body", url)
        return None


def first_str(value: Any) -> Optional[str]:
    """Coerce a provider field that may be a str, a single-element list, or
    missing, into a plain string (or None). Never fabricates a value."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item:
                return item
        return None
    return str(value)
