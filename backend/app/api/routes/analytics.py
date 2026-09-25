"""Analytics endpoints (Phase 8)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.models import User
from app.services.analytics import analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/analytics", summary="Aggregate analytics over stored articles")
def analytics(
    db: Session = Depends(get_db),
    provider: str | None = Query(None),
    category: str | None = Query(None),
    state: str | None = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    # Article corpus analytics are global/shared, but personal counts
    # (searches, bookmarks) are scoped to the caller so one user can never
    # observe another user's activity.
    uid = current_user.id if current_user is not None else None
    return analytics_service.get_overview(
        db, provider=provider, category=category, state=state, user_id=uid
    )


@router.get("/analytics/trend", summary="Compare article volume across two periods")
def trend(
    db: Session = Depends(get_db),
    current_from: str = Query(...),
    current_to: str = Query(...),
    previous_from: str = Query(...),
    previous_to: str = Query(...),
):
    return analytics_service.trend_comparison(
        db,
        current_from=current_from,
        current_to=current_to,
        previous_from=previous_from,
        previous_to=previous_to,
    )
