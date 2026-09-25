"""NewsData.io API collector.

Refactored from the notebook's ``fetch_newsdata``. The API key is injected by
the caller (never read from source / never exposed to the frontend).

Provider limitation (documented honestly): NewsData's free plan restricts how
far back results reach and which fields are returned (full historical
date-range search requires a paid tier). We send ``from_date``/``to_date``
when the user provides a range but do not claim it is enforced on every plan.
"""
from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.schemas.article import Article
from app.services.news.base import SearchContext, http_get_json, first_str

logger = get_logger("app.services.news.newsdata")

PROVIDER = "newsdata"
ENDPOINT = "https://newsdata.io/api/1/news"


def collect(ctx: SearchContext, *, api_key: Optional[str]) -> list[Article]:
    if not api_key:
        logger.warning("NewsData API key not configured; skipping provider.")
        return []

    params: dict[str, object] = {
        "apikey": api_key,
        "q": ctx.query,
        "country": ctx.country,
        "language": ctx.language,
    }
    if ctx.from_date:
        params["from_date"] = ctx.from_date
    if ctx.to_date:
        params["to_date"] = ctx.to_date
    if ctx.max_results:
        params["size"] = ctx.max_results

    data = http_get_json(ENDPOINT, params)
    if not data:
        return []

    results = data.get("results", [])
    if ctx.max_results and ctx.max_results > 0:
        results = results[: ctx.max_results]

    articles: list[Article] = []
    for item in results:
        articles.append(
            Article(
                title=item.get("title", "") or "",
                description=item.get("description"),
                url=item.get("url", "") or "",
                source=first_str(item.get("source_id")) or first_str(item.get("source")),
                provider=PROVIDER,
                author=first_str(item.get("author")),
                published_at=item.get("pubDate"),
                keyword_matched=ctx.query,
                image_url=item.get("image") or item.get("image_url"),
                language=first_str(item.get("language")) or ctx.language,
                country=first_str(item.get("country")) or ctx.country,
            )
        )

    logger.info("NewsData collected %d articles", len(articles))
    return articles
