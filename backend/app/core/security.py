"""Password hashing + JWT access tokens (Phase 12 - Auth).

Deliberately low-dependency and safe on Python 3.14:

* Password hashing uses the **standard library** :func:`hashlib.scrypt` (a
  memory-hard KDF) with a per-password random salt and constant-time
  comparison. No bcrypt/argon2 binary wheels are required.
* Tokens are **HS256 JWTs** via PyJWT (pure Python; the HMAC path needs no
  ``cryptography`` backend). The signing key comes from ``settings.secret_key``
  and is never hard-coded or logged.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from app.core.config import get_settings

# scrypt parameters (n must be a power of two). Tuned for a security-minded
# student project: ~16 MB memory cost per hash, ~tens of ms.
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16
_ALGORITHM = "HS256"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def hash_password(password: str) -> str:
    """Return a self-describing ``scrypt$N$r$p$salt$hash`` digest string."""
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "$".join(
        ["scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P), _b64(salt), _b64(dk)]
    )


def verify_password(password: str, hashed: Optional[str]) -> bool:
    """Constant-time verification against a stored scrypt digest."""
    if not hashed:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = hashed.split("$")
        if scheme != "scrypt":
            return False
        salt = _unb64(salt_b64)
        expected = _unb64(hash_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError, IndexError, binascii.Error):  # malformed digest -> no crash
        return False
    return hmac.compare_digest(candidate, expected)


def create_access_token(
    subject: str | int,
    *,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: Dict[str, Any] = {"sub": str(subject), "iat": now, "exp": expire}
    # ``iat`` is second-granular (JWT standard). We add a sub-second issuance
    # stamp so password-change token invalidation is exact and race-free.
    payload["iatf"] = now.timestamp()
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode + verify a token. Raises ``jwt.PyJWTError`` on any problem."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])


def generate_reset_token() -> str:
    """A high-entropy, single-use password-reset token (returned once, in email)."""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """Fast hash for a high-entropy reset token.

    scrypt is reserved for low-entropy *passwords*; the reset token is already
    ~256 bits of randomness, so a plain SHA-256 is the right, fast choice and
    still reveals nothing if the stored value leaks.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
