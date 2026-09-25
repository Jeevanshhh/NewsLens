"""Auth + account-lifecycle endpoints (Phase 12, extended by Command 6).

Beyond register/login/me this carries the security-sensitive account actions:
change password, expiring password reset (request + confirm), account deletion
and personal data export. The login endpoint is brute-force throttled.

Design notes:
* Password-reset tokens are never returned to an HTTP caller - they are handed
  straight to :mod:`app.services.email_service`. Both the "requested an account
  that exists" and "requested one that doesn't" cases yield the identical 202
  response (no user enumeration).
* Changing or resetting a password sets ``password_changed_at``, which the auth
  dependency uses to reject tokens minted beforehand (sign-out everywhere).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowLimiter, client_identity
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.services import email_service, user_service

router = APIRouter(tags=["auth"])

# Shared in-process throttle for failed logins (see rate_limit.py for the
# single-worker boundary + documented Redis upgrade path).
_s = get_settings()
login_limiter = SlidingWindowLimiter(_s.login_max_attempts, _s.login_window_seconds)

_RESET_SENT = {"detail": "if that email is registered, a reset link has been sent"}


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _issue_token(user: User) -> Token:
    return Token(
        access_token=create_access_token(user.id, extra_claims={"email": user.email}),
        user=UserOut(id=user.id, name=user.name, email=user.email),
    )


@router.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    try:
        user = user_service.create_user(db, payload)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    return _issue_token(user)


@router.post("/auth/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    key = client_identity(_client_host(request), payload.email)
    allowed, retry_after = login_limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts; try again later",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    user = user_service.authenticate(db, payload.email, payload.password)
    if user is None:
        # Same message for wrong-email and wrong-password (no enumeration).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_limiter.reset(key)  # success clears the failure window for this key
    return _issue_token(user)


@router.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut(id=current_user.id, name=current_user.name, email=current_user.email)


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        user_service.change_password(
            db,
            current_user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="current password is incorrect")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    token = user_service.begin_password_reset(db, payload.email)
    if token is not None:
        reset_url = f"{get_settings().public_frontend_url}/reset-password?token={token}"
        email_service.send_password_reset(payload.email, reset_url)
    # Identical response whether or not the account exists.
    return _RESET_SENT


@router.post("/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    user = user_service.complete_password_reset(
        db, token=payload.token, new_password=payload.new_password
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired reset token")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me/data")
def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = user_service.export_personal_data(db, current_user)
    return JSONResponse(
        data,
        headers={"Content-Disposition": 'attachment; filename="newslens-my-data.json"'},
    )


@router.delete("/auth/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_service.delete_account(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
