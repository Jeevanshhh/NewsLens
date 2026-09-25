"""Auth request/response schemas (Phase 12)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Simple, dependency-free email shape check (avoids pulling email-validator).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value) or len(value) > 255:
        raise ValueError("invalid email address")
    return value


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _valid_email(v)

    @field_validator("password")
    @classmethod
    def _no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("password must not be blank")
        return v


class UserLogin(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _valid_email(v)


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _valid_new_password(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("password must not be blank")
    return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_new(cls, v: str) -> str:
        return _valid_new_password(v)


class PasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _valid_email(v)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_new(cls, v: str) -> str:
        return _valid_new_password(v)
