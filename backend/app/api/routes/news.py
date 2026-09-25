"""Live Brief / current-headlines endpoint.

Returns *real* current top headlines fetched live from the configured Google
News RSS provider (no API key required). Nothing is fabricated or cached: if
the provider is unreachable the endpoint degrades to an empty list so the
frontend can render an empty state rather than an error.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_settings_dep
from app.services.news import google_news
from app.services.processing.normalizer import normalize_article

router = APIRouter(tags=["news"])


@router.get("/news/live", summary="Current top headlines (live provider fetch)")
def live_headlines(
    limit: int = Query(8, ge=1, le=25),
    settings=Depends(get_settings_dep),
):
    articles = google_news.fetch_top_headlines(
        limit=limit,
        rss_language=settings.rss_language,
        rss_country=settings.rss_country,
    )
    items = []
    for a in articles:
        clean = normalize_article(a)
        items.append(
            {
                "title": clean.title,
                "url": clean.url,
                "source": clean.source,
                "provider": clean.provider,
                "published_at": clean.published_at,
                "image_url": clean.image_url,
            }
        )
    return {"items": items, "count": len(items), "provider": google_news.PROVIDER}
