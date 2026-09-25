"""Analytics service (Phase 8).

Computes distributions and a timeline from the *actual* stored data via SQL
GROUP BY. No statistics are ever invented or hard-coded.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Article


def _count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _count_owned(db: Session, model, user_id: Optional[int]) -> int:
    """Count a user's own rows.

    Personal metrics (searches, bookmarks) must never leak across accounts, so
    they are scoped to the authenticated user. ``user_id is None`` maps to the
    anonymous scope (``user_id IS NULL``) - the same convention the search and
    bookmark services use - rather than an unscoped global count.
    """
    stmt = select(func.count()).select_from(model)
    stmt = stmt.where(model.user_id == user_id) if user_id is not None else stmt.where(
        model.user_id.is_(None)
    )
    return db.scalar(stmt) or 0


def _filtered(stmt, filters: dict):
    if filters.get("provider"):
        stmt = stmt.where(Article.provider == filters["provider"])
    if filters.get("category"):
        stmt = stmt.where(Article.category == filters["category"])
    if filters.get("state"):
        stmt = stmt.where(Article.state == filters["state"])
    return stmt


def _distribution(db: Session, column, filters: dict) -> List[dict]:
    stmt = select(column, func.count()).group_by(column)
    stmt = _filtered(stmt, filters)
    rows = db.execute(stmt.order_by(func.count().desc())).all()
    return [{"key": key, "count": count} for key, count in rows]


def get_overview(db: Session, *, provider=None, category=None, state=None, user_id: Optional[int] = None) -> dict:
    from app.models import Bookmark, Search

    filters = {"provider": provider, "category": category, "state": state}

    total_stmt = select(func.count()).select_from(Article)
    total_stmt = _filtered(total_stmt, filters)
    total_articles = db.scalar(total_stmt) or 0

    # Distinct publisher URLs in scope (honest; equals total under our URL dedup).
    unique_stmt = select(func.count(func.distinct(Article.url)))
    unique_stmt = _filtered(unique_stmt, filters)
    unique_articles = db.scalar(unique_stmt) or 0

    # Distinct active providers in scope.
    source_stmt = select(func.count(func.distinct(Article.provider)))
    source_stmt = _filtered(source_stmt, filters)
    source_count = db.scalar(source_stmt) or 0

    # Timeline by publication day (NULL dates excluded automatically).
    day = func.date(Article.published_date)
    timeline_stmt = select(day, func.count()).group_by(day).order_by(day)
    timeline_stmt = _filtered(timeline_stmt, filters)
    timeline = [
        {"date": str(d), "count": c} for d, c in db.execute(timeline_stmt).all() if d is not None
    ]

    return {
        "total_articles": total_articles,
        "unique_articles": unique_articles,
        "source_count": source_count,
        "search_count": _count_owned(db, Search, user_id),
        "bookmark_count": _count_owned(db, Bookmark, user_id),
        "by_provider": _distribution(db, Article.provider, filters),
        "by_category": _distribution(db, Article.category, filters),
        "by_state": _distribution(db, Article.state, filters),
        "by_exam": _distribution(db, Article.name_of_exam, filters),
        "timeline": timeline,
    }


def trend_comparison(
    db: Session, *, current_from: str, current_to: str, previous_from: str, previous_to: str
) -> dict:
    """Compare article counts between two date windows (documented methodology).

    percentage_change = ((current - previous) / previous) * 100, with safe
    handling of division by zero (returns None when previous == 0).
    """
    def _count(start: str, end: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Article)
            .where(func.date(Article.published_date) >= start)
            .where(func.date(Article.published_date) <= end)
        )
        return db.scalar(stmt) or 0

    current = _count(current_from, current_to)
    previous = _count(previous_from, previous_to)
    pct = None if previous == 0 else round(((current - previous) / previous) * 100, 2)
    return {
        "current": current,
        "previous": previous,
        "percentage_change": pct,
        "method": "article_count_by_published_date",
    }
