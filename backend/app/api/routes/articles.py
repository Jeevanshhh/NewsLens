"""Article listing / detail endpoints with filter, sort, pagination (Phase 5)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.models import User
from app.services import article_repo

router = APIRouter(tags=["articles"])


@router.get("/articles", summary="List stored articles")
def list_articles(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    provider: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    name_of_exam: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    search_id: Optional[int] = Query(None, ge=1),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    filters = {
        "provider": provider,
        "category": category,
        "state": state,
        "source": source,
        "language": language,
        "country": country,
        "name_of_exam": name_of_exam,
        "q": q,
    }
    items, total = article_repo.list_articles(
        db, filters=filters, sort=sort, page=page, page_size=page_size, search_id=search_id
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


@router.get("/articles/{article_id}", summary="Article detail")
def get_article(article_id: int, db: Session = Depends(get_db)):
    row = article_repo.get_by_id(db, article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    return article_repo.serialize(row)


@router.get("/articles/{article_id}/related", summary="Related coverage")
def get_related(
    article_id: int,
    db: Session = Depends(get_db),
    limit: int = Query(6, ge=1, le=20),
):
    row = article_repo.get_by_id(db, article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    items = article_repo.related(db, row, limit=limit)
    return {"items": items, "count": len(items)}
