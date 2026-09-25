"""Outbound email (currently only password-reset links).

The project deliberately has no hard dependency on a mail provider, and the
reset flow must be honest: we never *pretend* an email was delivered.

* When SMTP is configured (``settings.smtp_configured``) a real message is
  dispatched via the standard library :mod:`smtplib`.
* When it is not (local development / the offline test-suite), the fully
  rendered message is captured in an in-memory :data:`OUTBOX` so the flow is
  still end-to-end testable without a mail server.

A reset token is only ever placed inside the email body (or the outbox) - it is
**never** returned in an HTTP response, so a caller cannot learn, by probing,
whether a given address exists.
"""
from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, List

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.services.email")

# Rendered messages captured instead of sent, when SMTP is not configured.
# Cleared between tests; never exposed over HTTP.
OUTBOX: List[Dict[str, str]] = []


def _render(to_email: str, reset_url: str) -> tuple[str, str]:
    minutes = get_settings().password_reset_expire_minutes
    subject = "Reset your NewsLens password"
    body = (
        "You (or someone else) asked to reset the password for the NewsLens\n"
        "account associated with this address.\n\n"
        f"Open the link below to choose a new password. It expires in {minutes}\n"
        "minutes and can be used only once:\n\n"
        f"    {reset_url}\n\n"
        "If you did not request a password reset you can safely ignore this\n"
        "email - your current password will continue to work.\n"
    )
    return subject, body


def send_password_reset(to_email: str, reset_url: str) -> bool:
    """Dispatch a password-reset email; return True only if actually sent.

    Returns False when SMTP is unconfigured (the message is recorded in the
    dev :data:`OUTBOX`) and also when a real send fails, so the caller can
    always respond with the same generic, non-enumerating message.
    """
    settings = get_settings()
    subject, body = _render(to_email, reset_url)

    if not settings.smtp_configured:
        OUTBOX.append(
            {
                "to": to_email,
                "subject": subject,
                "body": body,
                "url": reset_url,
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        return False

    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 - a mail outage must not 500 the request
        # Log the failure without ever logging the token/URL it contains.
        logger.exception("Failed to send password-reset email")
        return False


def clear_outbox() -> None:
    """Empty the development outbox (used between tests)."""
    OUTBOX.clear()
