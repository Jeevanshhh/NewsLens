"""User model.

Beyond identity (name/email/password hash) this carries the fields the account
lifecycle needs: ``password_changed_at`` (to invalidate tokens minted before a
password change/reset) and a single-use, expiring password-reset token stored
only as a hash.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models._mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Hashed only - never plaintext (populated in the Auth phase).
    password_hash: Mapped[str] = mapped_column(String(255), default="")

    # Session/token handling: access tokens issued before this instant are
    # rejected. Set on password change and on completed reset.
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Password-reset flow. The raw token is never stored - only its hash and a
    # short expiry. Both are cleared once the reset is used (single-use).
    reset_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
