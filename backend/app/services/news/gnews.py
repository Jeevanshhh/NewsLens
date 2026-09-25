"""GNews API collector.

Refactored from the notebook's ``fetch_gnews``. The API key is injected by the
caller (never read from source / never exposed to the frontend).

Provider limitation (documented honestly): GNews' free plan only returns
recently published articles and may ignore the ``from``/``to`` date range
(full historical filtering requires a paid tier). We still send the range when
the user requests it, but do not claim it is enforced on every plan.
"""
from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.schemas.article import Article
from app.services.news.base import SearchContext, http_get_json, first_str

logger = get_logger("app.services.news.gnews")

PROVIDER = "gnews"
ENDPOINT = "https://gnews.io/api/v4/search"


def collect(ctx: SearchContext, *, api_key: Optional[str]) -> list[Article]:
    if not api_key:
        logger.warning("GNews API key not configured; skipping provider.")
        return []

    params: dict[str, object] = {
        "q": ctx.query,
        "lang": ctx.language,
        "country": ctx.country,
        "max": ctx.max_results,
        "token": api_key,
    }
    if ctx.from_date:
        params["from"] = f"{ctx.from_date}T00:00:00Z"
    if ctx.to_date:
        params["to"] = f"{ctx.to_date}T23:59:59Z"

    data = http_get_json(ENDPOINT, params)
    if not data:
        return []

    articles: list[Article] = []
    for item in data.get("articles", []):
        source_obj = item.get("source")
        source_name = (
            source_obj.get("name") if isinstance(source_obj, dict) else first_str(source_obj)
        )
        articles.append(
            Article(
                title=item.get("title", "") or "",
                description=item.get("description"),
                url=item.get("url", "") or "",
                source=source_name,
                provider=PROVIDER,
                author=first_str(item.get("author")),
                published_at=item.get("publishedAt"),
                keyword_matched=ctx.query,
                image_url=item.get("image"),
                language=ctx.language,
                country=ctx.country,
            )
        )

    logger.info("GNews collected %d articles", len(articles))
    return articles
