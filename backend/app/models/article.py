"""Article ORM model + mapping from a processed article."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models._mixins import TimestampMixin
from app.schemas.processed_article import ProcessedArticle
from app.services.processing.normalizer import normalize_datetime


class Article(Base, TimestampMixin):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_category", "category"),
        Index("ix_articles_state", "state"),
        Index("ix_articles_provider", "provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Core content
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)

    # Attribution / provider
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="")
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timing
    published_at: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # raw
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Search linkage / locale
    keyword_matched: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Domain classification (rule-based, ported from the notebook)
    name_of_exam: Mapped[str] = mapped_column(String(128), default="Unknown")
    exam_category: Mapped[str] = mapped_column(String(128), default="Unknown")
    board: Mapped[str] = mapped_column(String(128), default="Unknown")
    conducted_by: Mapped[str] = mapped_column(String(128), default="Unknown")
    pbt_cbt: Mapped[str] = mapped_column(String(32), default="Unknown")
    state: Mapped[str] = mapped_column(String(128), default="Unknown")
    conducted_in: Mapped[str] = mapped_column(String(128), default="Unknown")
    category: Mapped[str] = mapped_column(String(128), default="Other")
    reason: Mapped[str] = mapped_column(Text, default="")
    exam_year: Mapped[str] = mapped_column(String(8), default="")

    @classmethod
    def from_processed(cls, pa: ProcessedArticle) -> "Article":
        return cls(
            title=pa.title,
            description=pa.description,
            url=pa.url,
            source=pa.source,
            provider=pa.provider,
            author=pa.author,
            published_at=pa.published_at,
            published_date=normalize_datetime(pa.published_date or pa.published_at),
            keyword_matched=pa.keyword_matched,
            language=pa.language,
            country=pa.country,
            image_url=pa.image_url,
            name_of_exam=pa.name_of_exam,
            exam_category=pa.exam_category,
            board=pa.board,
            conducted_by=pa.conducted_by,
            pbt_cbt=pa.pbt_cbt,
            state=pa.state,
            conducted_in=pa.conducted_in,
            category=pa.category,
            reason=pa.reason,
            exam_year=pa.exam_year,
        )
