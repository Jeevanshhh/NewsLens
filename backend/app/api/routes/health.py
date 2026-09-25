"""Health / readiness endpoint.

Reports operational status and whether providers are configured, WITHOUT
ever returning the secret values themselves (only booleans).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


@router.get("/health", summary="Service health / readiness")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": APP_VERSION,
        "environment": settings.app_env,
        "providers": {
            "google_news_rss": True,  # no key required
            "gnews": settings.gnews_configured,
            "newsdata": settings.newsdata_configured,
        },
    }


@router.get("/health/ready", summary="Readiness (database connectivity)")
def ready(response: Response, db: Session = Depends(get_db)) -> dict:
    """Confirm the database is reachable, without ever exposing the URL.

    Returns 503 (and ``status: "unavailable"``) if the health check query fails,
    so an orchestrator's readiness probe can take the instance out of rotation.
    """
    try:
        db.execute(text("SELECT 1"))
        db_up = True
    except SQLAlchemyError:
        db_up = False
    if not db_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if db_up else "unavailable", "database": "up" if db_up else "down"}
