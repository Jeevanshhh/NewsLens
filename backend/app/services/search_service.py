"""Search orchestration: collect -> process -> persist (Phase 5).

Collectors are injectable so this can be unit-tested with no network and no
real API keys. In production the default collectors read provider keys from
settings (env vars) - keys never reach the frontend.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Search
from app.schemas.search import SearchRequest
from app.services import article_repo
from app.services.news import gnews, google_news, newsdata
from app.services.news.base import SearchContext
from app.services.processing import pipeline
from app.services.processing.domain_config import ClassificationConfig

Collector = Callable[[SearchContext], List]


def _rss_language(ctx: SearchContext) -> str:
    return f"{ctx.language}-{ctx.country.upper()}"


def default_collectors(settings: Settings) -> Dict[str, Collector]:
    return {
        "google_news": lambda ctx: google_news.collect(
            ctx, rss_language=_rss_language(ctx), rss_country=ctx.country.upper()
        ),
        "gnews": lambda ctx: gnews.collect(ctx, api_key=settings.gnews_api_key),
        "newsdata": lambda ctx: newsdata.collect(ctx, api_key=settings.newsdata_api_key),
    }


def _to_ctx(req: SearchRequest) -> SearchContext:
    return SearchContext(
        query=req.query,
        from_date=req.from_date.isoformat() if req.from_date else None,
        to_date=req.to_date.isoformat() if req.to_date else None,
        country=req.country,
        language=req.language,
        max_results=req.max_results,
    )


def run_search(
    db: Session,
    req: SearchRequest,
    *,
    settings: Optional[Settings] = None,
    collectors: Optional[Dict[str, Collector]] = None,
    config: Optional[ClassificationConfig] = None,
    user_id: Optional[int] = None,
) -> dict:
    settings = settings or get_settings()
    collectors = collectors or default_collectors(settings)

    ctx = _to_ctx(req)

    # Build the classification config from settings when the caller did not
    # inject one, so live searches can use the supervised topic-model fallback
    # while low-level tests keep the deterministic rule-only behaviour.
    if config is None:
        config = ClassificationConfig(topic_model_enabled=settings.enable_topic_model)

    collected = 0
    raw: List = []
    per_provider: Dict[str, int] = {}
    for provider in req.sources:
        fn = collectors.get(provider)
        if fn is None:
            continue
        found = fn(ctx)
        per_provider[provider] = len(found)
        raw.extend(found)
        collected += len(found)

    # dedup across providers + rule-based enrichment happen in the pipeline
    processed = pipeline.process(raw, config)

    rows, new_count = article_repo.upsert_articles(db, processed)

    search = Search(
        user_id=user_id,
        query=req.query,
        from_date=req.from_date.isoformat() if req.from_date else None,
        to_date=req.to_date.isoformat() if req.to_date else None,
        filters={
            "sources": req.sources,
            "country": req.country,
            "language": req.language,
            "category": req.category,
            "state": req.state,
        },
        result_count=len(processed),
    )
    db.add(search)
    db.flush()
    article_repo.link_search(db, search.id, rows)
    db.commit()

    return {
        "search_id": search.id,
        "query": req.query,
        "total_collected": collected,
        "unique_results": len(processed),
        "new_stored": new_count,
        "per_provider": per_provider,
    }
