"""Search history + saved searches, and the search<->article link table."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, String, Table, Column, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models._mixins import TimestampMixin

search_results = Table(
    "search_results",
    Base.metadata,
    Column("search_id", ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True),
    Column("article_id", ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
)


class Search(Base, TimestampMixin):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query: Mapped[str] = mapped_column(String(512))
    from_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    # A saved search is just a named search the user chose to keep.
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_saved: Mapped[bool] = mapped_column(Integer, default=0)

    articles: Mapped[list["Article"]] = relationship(  # noqa: F821
        secondary=search_results, backref="searches"
    )
