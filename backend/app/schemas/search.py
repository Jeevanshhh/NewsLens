"""Search request/response schemas."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

VALID_SOURCES = {"google_news", "gnews", "newsdata"}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    sources: List[str] = Field(default_factory=lambda: ["google_news"])
    country: str = Field(default="in", max_length=8)
    language: str = Field(default="en", max_length=8)
    category: Optional[str] = None
    state: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def _validate(self) -> "SearchRequest":
        self.query = self.query.strip()
        if not self.query:
            raise ValueError("query must not be blank")
        if not self.sources:
            raise ValueError("at least one source must be selected")
        unknown = set(self.sources) - VALID_SOURCES
        if unknown:
            raise ValueError(f"unknown sources: {sorted(unknown)}")
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        return self
