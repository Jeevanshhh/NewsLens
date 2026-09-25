"""Bookmark request/response schemas (Phase 10)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class BookmarkCreate(BaseModel):
    article_id: int = Field(ge=1)


class BookmarkOut(BaseModel):
    bookmark_id: int
    article_id: int
    bookmarked_at: str | None = None
    article: dict
