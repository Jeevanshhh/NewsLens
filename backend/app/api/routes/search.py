"""Search + history endpoints (Phase 5, per-user history in Phase 12).

Searches a caller runs are recorded under their account when a bearer token is
present; otherwise they belong to the anonymous scope. History reads/mutations
are always limited to the caller's own scope.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_collectors, get_current_user_optional, get_db, get_settings_dep
from app.models import Search, User
from app.schemas.search import SearchRequest
from app.services import search_service

router = APIRouter(tags=["search"])


def _uid(current_user: Optional[User]) -> Optional[int]:
    return current_user.id if current_user is not None else None


def _owned(db: Session, search_id: int, uid: Optional[int]) -> Search:
    s = db.get(Search, search_id)
    if s is None or s.user_id != uid:
        # Same 404 whether missing or owned by someone else (no existence leak).
        raise HTTPException(status_code=404, detail="search not found")
    return s


@router.post("/search", summary="Run a multi-source news search")
def create_search(
    req: SearchRequest,
    db: Session = Depends(get_db),
    collectors=Depends(get_collectors),
    settings=Depends(get_settings_dep),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    try:
        return search_service.run_search(
            db, req, settings=settings, collectors=collectors, user_id=_uid(current_user)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/searches", summary="Search history")
def list_searches(
    db: Session = Depends(get_db),
    saved_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    uid = _uid(current_user)
    stmt = select(Search)
    stmt = stmt.where(Search.user_id == uid) if uid is not None else stmt.where(
        Search.user_id.is_(None)
    )
    if saved_only:
        stmt = stmt.where(Search.is_saved == 1)
    stmt = stmt.order_by(desc(Search.id)).offset(offset).limit(limit)
    rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": s.id,
                "query": s.query,
                "from_date": s.from_date,
                "to_date": s.to_date,
                "filters": s.filters,
                "result_count": s.result_count,
                "name": s.name,
                "is_saved": bool(s.is_saved),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ],
        "count": len(rows),
    }


@router.post("/searches/{search_id}/save", summary="Save a search")
def save_search(
    search_id: int,
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    s = _owned(db, search_id, _uid(current_user))
    s.is_saved = 1
    if name:
        s.name = name
    db.commit()
    return {"id": s.id, "is_saved": True, "name": s.name}


@router.post("/searches/{search_id}/unsave", summary="Remove a search from saved")
def unsave_search(
    search_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    s = _owned(db, search_id, _uid(current_user))
    s.is_saved = 0
    db.commit()
    return {"id": s.id, "is_saved": False, "name": s.name}


@router.delete("/searches/{search_id}", summary="Delete a search from history")
def delete_search(
    search_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    s = _owned(db, search_id, _uid(current_user))
    db.delete(s)
    db.commit()
    return {"deleted": True, "id": search_id}
