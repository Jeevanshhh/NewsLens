"""Google News RSS collector (no API key required).

Refactored from the notebook's ``fetch_google_news``. Uses the public Google
News RSS search feed. Unlike the two keyed APIs, Google News RSS natively
supports date scoping via ``after:`` / ``before:`` query operators, which we
apply when a date range is provided.
"""
from __future__ import annotations

import datetime
from urllib.parse import quote

import feedparser

from app.core.logging import get_logger
from app.schemas.article import Article
from app.services.news.base import SearchContext, first_str

logger = get_logger("app.services.news.google_news")

PROVIDER = "google_news"
BASE_URL = "https://news.google.com/rss/search"
# The default (no-query) Google News feed returns current top headlines.
TOP_STORIES_URL = "https://news.google.com/rss"


def _extract_image(item) -> str | None:
    """Best-effort thumbnail URL from a Google News RSS entry.

    Google attaches the publisher image via ``media:thumbnail`` / ``media:content``
    (exposed by feedparser as ``media_thumbnail`` / ``media_content``) or an
    ``image`` link. Returns ``None`` when the entry genuinely has no image - we
    never fabricate a thumbnail.
    """
    for key in ("media_thumbnail", "media_content"):
        arr = item.get(key)
        if isinstance(arr, (list, tuple)) and arr:
            url = arr[0].get("url") if isinstance(arr[0], dict) else None
            if url:
                return url
    image = item.get("image")
    if isinstance(image, dict):
        href = image.get("href")
        if href:
            return href
    for enc in item.get("enclosures") or []:
        if isinstance(enc, dict) and str(enc.get("type", "")).startswith("image"):
            return enc.get("url")
    return None


def _build_query(ctx: SearchContext) -> str:
    """Append Google News date operators when a range is supplied."""
    parts = [ctx.query]
    if ctx.from_date:
        parts.append(f"after:{ctx.from_date}")
    if ctx.to_date:
        # ``before:`` is exclusive at midnight, so a same-day range
        # (from == to) was an empty interval and "today" searches always
        # returned zero results. Shift the bound by +1 day to make the
        # user's to_date inclusive (QA bug found in mass-search pass).
        try:
            end = datetime.date.fromisoformat(ctx.to_date) + datetime.timedelta(days=1)
            parts.append(f"before:{end.isoformat()}")
        except ValueError:
            parts.append(f"before:{ctx.to_date}")
    return " ".join(p for p in parts if p)


def collect(
    ctx: SearchContext,
    *,
    rss_language: str = "en-IN",
    rss_country: str = "IN",
) -> list[Article]:
    query = _build_query(ctx)
    ceid = f"{rss_country}:{rss_language.split('-')[0]}"
    url = (
        f"{BASE_URL}?q={quote(query)}"
        f"&hl={rss_language}&gl={rss_country}&ceid={ceid}"
    )

    try:
        feed = feedparser.parse(url)
    except Exception as exc:  # feedparser rarely raises; guard anyway
        logger.warning("Google News RSS parse failed: %s", exc)
        return []

    entries = feed.entries
    if ctx.max_results and ctx.max_results > 0:
        entries = entries[: ctx.max_results]

    articles: list[Article] = []
    for item in entries:
        source_obj = item.get("source")
        source_name = (
            source_obj.get("title") if isinstance(source_obj, dict) else first_str(source_obj)
        )
        articles.append(
            Article(
                title=item.get("title", "") or "",
                description=item.get("summary"),
                url=item.get("link", "") or "",
                source=source_name,
                provider=PROVIDER,
                author=first_str(item.get("author")),
                published_at=item.get("published"),
                keyword_matched=ctx.query,
                language=rss_language,
                country=rss_country,
                image_url=_extract_image(item),
            )
        )

    logger.info("Google News RSS collected %d articles", len(articles))
    return articles


def fetch_top_headlines(
    *,
    limit: int = 8,
    rss_language: str = "en",
    rss_country: str = "IN",
) -> list[Article]:
    """Return current top headlines from the public Google News RSS feed.

    This is *real* data fetched live from the provider (no API key required);
    nothing is cached or invented. On any failure it degrades to an empty list
    so the caller can show an empty state rather than an error screen.
    """
    lang = rss_language if "-" in rss_language else f"{rss_language}-{rss_country}"
    ceid = f"{rss_country}:{rss_language}"
    url = f"{TOP_STORIES_URL}?hl={lang}&gl={rss_country}&ceid={ceid}"

    try:
        feed = feedparser.parse(url)
    except Exception as exc:  # feedparser rarely raises; guard anyway
        logger.warning("Google News top-headlines parse failed: %s", exc)
        return []

    articles: list[Article] = []
    for item in feed.entries[: max(1, limit)]:
        source_obj = item.get("source")
        source_name = (
            source_obj.get("title") if isinstance(source_obj, dict) else first_str(source_obj)
        )
        articles.append(
            Article(
                title=item.get("title", "") or "",
                description=item.get("summary"),
                url=item.get("link", "") or "",
                source=source_name,
                provider=PROVIDER,
                published_at=item.get("published"),
                language=rss_language,
                country=rss_country,
                image_url=_extract_image(item),
            )
        )
    logger.info("Google News top-headlines returned %d entries", len(articles))
    return articles
