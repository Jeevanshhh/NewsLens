"""Bookmarks endpoints (Phase 10, per-user in Phase 12).

Lets a user keep articles of interest. Bookmarks are idempotent (bookmarking
twice is a no-op). When a valid bearer token is present the bookmarks are
scoped to that user; otherwise they live in the anonymous scope (user_id NULL).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.models import User
from app.schemas.bookmark import BookmarkCreate
from app.services import bookmark_service

router = APIRouter(tags=["bookmarks"])


def _uid(current_user: Optional[User]) -> Optional[int]:
    return current_user.id if current_user is not None else None


@router.get("/bookmarks", summary="List bookmarked articles")
def list_bookmarks(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    items = bookmark_service.list_bookmarks(db, user_id=_uid(current_user))
    return {"items": items, "count": len(items)}


@router.get("/bookmarks/status", summary="Bookmark status for a set of article ids")
def bookmark_status(
    ids: str = Query(..., description="comma-separated article ids"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=422, detail="ids must be comma-separated integers")
    marked = bookmark_service.bookmarked_ids(db, id_list, user_id=_uid(current_user))
    return {"status": {str(i): (i in marked) for i in id_list}}


@router.post("/bookmarks", summary="Bookmark an article", status_code=201)
def add_bookmark(
    payload: BookmarkCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    try:
        result = bookmark_service.add(db, payload.article_id, user_id=_uid(current_user))
    except ValueError:
        raise HTTPException(status_code=404, detail="article not found")
    if not result["created"]:
        # Already bookmarked - no duplicate created, so report 200, not 201.
        response.status_code = 200
        return {"created": False, "bookmark": result["bookmark"]}
    return {"created": True, "bookmark": result["bookmark"]}


@router.delete("/bookmarks/{article_id}", summary="Remove a bookmark")
def remove_bookmark(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    removed = bookmark_service.remove(db, article_id, user_id=_uid(current_user))
    if not removed:
        raise HTTPException(status_code=404, detail="bookmark not found")
    return {"deleted": True, "article_id": article_id}
