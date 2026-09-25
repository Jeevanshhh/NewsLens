"""Bookmark persistence + querying (Phase 10).

`user_id` is optional throughout: while auth (Phase 12) is not wired yet all
bookmarks live in the anonymous scope (user_id IS NULL), but the signatures are
already forward-compatible so enabling auth won't require re-plumbing.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Bookmark
from app.services import article_repo


def _scope(stmt, user_id: Optional[int]):
    return stmt.where(Bookmark.user_id == user_id) if user_id is not None else stmt.where(
        Bookmark.user_id.is_(None)
    )


def _row(db: Session, bookmark: Bookmark) -> dict:
    article = db.get(Article, bookmark.article_id)
    return {
        "bookmark_id": bookmark.id,
        "article_id": bookmark.article_id,
        "bookmarked_at": bookmark.created_at.isoformat() if bookmark.created_at else None,
        "article": article_repo.serialize(article) if article else None,
    }


def list_bookmarks(db: Session, *, user_id: Optional[int] = None) -> List[dict]:
    stmt = _scope(select(Bookmark).order_by(Bookmark.id.desc()), user_id)
    return [_row(db, b) for b in db.scalars(stmt).all()]


def is_bookmarked(db: Session, article_id: int, *, user_id: Optional[int] = None) -> bool:
    stmt = _scope(select(Bookmark).where(Bookmark.article_id == article_id), user_id)
    return db.scalar(stmt.limit(1)) is not None


def bookmarked_ids(db: Session, article_ids: Sequence[int], *, user_id: Optional[int] = None) -> Set[int]:
    """Return the subset of ``article_ids`` the current scope has bookmarked."""
    ids = [i for i in article_ids if i is not None]
    if not ids:
        return set()
    stmt = _scope(select(Bookmark.article_id).where(Bookmark.article_id.in_(ids)), user_id)
    return set(db.scalars(stmt).all())


def add(db: Session, article_id: int, *, user_id: Optional[int] = None) -> dict:
    """Idempotently bookmark an article; returns the (existing or new) record."""
    if db.get(Article, article_id) is None:
        raise ValueError("article not found")

    stmt = _scope(select(Bookmark).where(Bookmark.article_id == article_id), user_id)
    existing = db.scalar(stmt.limit(1))
    if existing is not None:
        return {"bookmark": _row(db, existing), "created": False}

    bookmark = Bookmark(article_id=article_id, user_id=user_id)
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return {"bookmark": _row(db, bookmark), "created": True}


def remove(db: Session, article_id: int, *, user_id: Optional[int] = None) -> bool:
    stmt = _scope(select(Bookmark).where(Bookmark.article_id == article_id), user_id)
    bookmark = db.scalar(stmt.limit(1))
    if bookmark is None:
        return False
    db.delete(bookmark)
    db.commit()
    return True
