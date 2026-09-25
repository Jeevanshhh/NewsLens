"""Deduplication (Phase 3).

Preserves the notebook's exact-URL deduplication behaviour, but is written
behind a pluggable key function so future strategies (normalized URL, title
similarity, content similarity) can be introduced without touching callers.
Articles with an empty URL are dropped (as in the original notebook).
"""
from __future__ import annotations

from typing import Callable, List

from app.schemas.article import Article

KeyFn = Callable[[Article], str]


def _url_key(article: Article) -> str:
    return (article.url or "").strip()


def deduplicate(
    articles: List[Article],
    key_fn: KeyFn = _url_key,
) -> List[Article]:
    seen: set[str] = set()
    result: List[Article] = []
    for article in articles:
        key = key_fn(article)
        if not key:          # no URL -> cannot dedupe; drop (matches notebook)
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(article)
    return result
