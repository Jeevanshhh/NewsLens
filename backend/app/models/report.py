"""Generated report records."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models._mixins import TimestampMixin


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(16))          # csv | xlsx | pdf | docx
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
