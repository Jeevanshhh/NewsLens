"""Reusable FastAPI dependencies."""
from __future__ import annotations

from datetime import timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.database import rls
from app.database.connection import get_db  # re-export for route imports
from app.models import User
from app.services import user_service
from app.services.search_service import default_collectors

# auto_error=False so an absent header yields None (lets us have optional-auth
# endpoints) instead of a hard 403 from the security scheme itself.
_bearer = HTTPBearer(auto_error=False)


def get_settings_dep() -> Settings:
    return get_settings()


def get_collectors():
    """Default (network) collectors; overridden in tests."""
    return default_collectors(get_settings())


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the logged-in user, or None when no/invalid token is supplied.

    An *absent* credential means anonymous (None). A *present but invalid*
    token is rejected with 401 so clients learn their token is bad.
    """
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Set the RLS scope from the JWT subject *before* the first query so the
    # transaction-local app.current_user_id is correct from the start. No-op on
    # SQLite (see app.database.rls).
    sub = payload.get("sub", "")
    rls.set_rls_user(db, int(sub) if str(sub).isdigit() else None)
    user = user_service.get_user(db, int(sub) if str(sub).isdigit() else 0)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Reject tokens minted before the last password change/reset, so changing a
    # password signs the user out everywhere. ``password_changed_at`` is None for
    # accounts that have never rotated, so this never invalidates a fresh token.
    if _token_issued_before_password_change(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _token_issued_before_password_change(payload: dict, user: User) -> bool:
    changed_at = getattr(user, "password_changed_at", None)
    if changed_at is None:
        return False
    # Prefer the sub-second ``iatf`` stamp; fall back to standard ``iat``.
    issued = payload.get("iatf", payload.get("iat"))
    if issued is None:
        return False
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    return changed_at.timestamp() > float(issued)


def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Require an authenticated user (401 otherwise)."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
