"""Structured (post-processing) article model.

Extends the raw :class:`~app.schemas.article.Article` with the rule-based
classification/extraction fields produced in Phase 3. Field names map to the
notebook's original output columns (kept for continuity and exports):

    Name of Exam, Exam Category, Board, State, Conducted In, Conducted By,
    Category, Reason, PBT/CBT, Exam Year, Published Date
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.article import Article


class ProcessedArticle(Article):
    # Exam / domain metadata
    name_of_exam: str = "Unknown"
    exam_category: str = "Unknown"
    board: str = "Unknown"
    conducted_by: str = "Unknown"
    pbt_cbt: str = "Unknown"

    # Geography
    state: str = "Unknown"
    conducted_in: str = "Unknown"

    # Classification + extraction
    category: str = "Other"
    reason: str = ""
    exam_year: str = ""

    # Normalized publication time (ISO 8601 UTC); raw kept in `published_at`.
    published_date: Optional[str] = Field(default=None)
