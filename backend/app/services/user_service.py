"""User registration, credential verification and account lifecycle.

The lifecycle helpers here back Command 6: change password, expiring single-use
password resets, account deletion (right to erasure) and personal data export
(data portability). Reset tokens are stored only as a hash and their raw value
is returned once to the caller that emails it - never to an HTTP response.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.models import Article, Bookmark, Report, Search, User
from app.models._mixins import utcnow
from app.schemas.auth import UserCreate


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to UTC. SQLite stores tz-naive values, so anything
    read back without a tzinfo is interpreted as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def create_user(db: Session, payload: UserCreate) -> User:
    """Create a user with a hashed password. Raises ValueError on duplicate email."""
    if get_by_email(db, payload.email) is not None:
        raise ValueError("email already registered")
    user = User(
        name=payload.name,
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    """Return the user if credentials match, else None (no user enumeration leak)."""
    user = get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


# ---- Account lifecycle ----------------------------------------------------
def change_password(db: Session, user: User, *, current_password: str, new_password: str) -> None:
    """Verify the current password then rotate it, invalidating older tokens."""
    if not verify_password(current_password, user.password_hash):
        raise ValueError("current password is incorrect")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    # Any outstanding reset link is moot once the password is changed.
    user.reset_token_hash = None
    user.reset_expires_at = None
    db.commit()


def begin_password_reset(db: Session, email: str) -> Optional[str]:
    """Create a single-use reset token for ``email`` and return the raw token.

    Returns ``None`` when no account matches, so the route can respond with the
    same generic message either way (no enumeration). The caller emails the
    token; it is never surfaced over HTTP.
    """
    user = get_by_email(db, email)
    if user is None:
        return None
    token = generate_reset_token()
    user.reset_token_hash = hash_reset_token(token)
    user.reset_expires_at = utcnow() + timedelta(
        minutes=get_settings().password_reset_expire_minutes
    )
    db.commit()
    return token


def complete_password_reset(db: Session, *, token: str, new_password: str) -> Optional[User]:
    """Consume a valid, unexpired reset token and set a new password.

    Returns the user on success or ``None`` for an unknown/expired/empty token
    (single-use: the token and its expiry are cleared on success).
    """
    if not token:
        return None
    user = db.scalar(select(User).where(User.reset_token_hash == hash_reset_token(token)))
    if user is None:
        return None
    if user.reset_expires_at is None or _as_utc(user.reset_expires_at) < utcnow():
        return None
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.reset_token_hash = None
    user.reset_expires_at = None
    db.commit()
    return user


def delete_account(db: Session, user: User) -> None:
    """Erase the account and everything it owns (right to erasure).

    Bookmarks, searches (and their search<->article links) and report records
    are deleted first; any on-disk report file referenced by a record is removed
    best-effort. Then the user row itself is deleted.
    """
    import os

    for bookmark in db.scalars(select(Bookmark).where(Bookmark.user_id == user.id)).all():
        db.delete(bookmark)
    for search in db.scalars(select(Search).where(Search.user_id == user.id)).all():
        db.delete(search)  # SQLAlchemy clears the search_results link rows
    for report in db.scalars(select(Report).where(Report.user_id == user.id)).all():
        if report.file_path:
            try:
                os.remove(report.file_path)
            except OSError:
                pass  # a missing/unwritable file must not block erasure
        db.delete(report)
    db.delete(user)
    db.commit()


def export_personal_data(db: Session, user: User) -> dict:
    """Return every piece of personal data the platform holds for ``user``.

    The article corpus itself is shared/global, so only the *user's own*
    searches, bookmarks (with the referenced article's public metadata) and
    report records are included - plus their profile.
    """
    searches: List[dict] = []
    for s in db.scalars(
        select(Search).where(Search.user_id == user.id).order_by(Search.created_at)
    ).all():
        searches.append(
            {
                "query": s.query,
                "name": s.name,
                "is_saved": bool(s.is_saved),
                "from_date": s.from_date,
                "to_date": s.to_date,
                "result_count": s.result_count,
                "created_at": _iso(s.created_at),
            }
        )

    bookmarks: List[dict] = []
    for b in db.scalars(
        select(Bookmark).where(Bookmark.user_id == user.id).order_by(Bookmark.created_at)
    ).all():
        article = db.get(Article, b.article_id)
        bookmarks.append(
            {
                "article_id": b.article_id,
                "title": article.title if article else None,
                "url": article.url if article else None,
                "source": article.source if article else None,
                "created_at": _iso(b.created_at),
            }
        )

    reports: List[dict] = []
    for r in db.scalars(
        select(Report).where(Report.user_id == user.id).order_by(Report.created_at)
    ).all():
        reports.append(
            {
                "name": r.name,
                "type": r.type,
                "parameters": r.parameters,
                "created_at": _iso(r.created_at),
            }
        )

    data: dict[str, Any] = {
        "profile": {
            "name": user.name,
            "email": user.email,
            "created_at": _iso(user.created_at),
        },
        "counts": {
            "searches": len(searches),
            "bookmarks": len(bookmarks),
            "reports": len(reports),
        },
        "searches": searches,
        "bookmarks": bookmarks,
        "reports": reports,
        "generated_at": utcnow().isoformat(timespec="seconds"),
    }
    return data


def _iso(value: Optional[datetime]) -> Optional[str]:
    return _as_utc(value).isoformat(timespec="seconds") if value is not None else None
