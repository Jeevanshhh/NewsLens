"""Command 6 - Account lifecycle + security tests. Fully offline.

Covers: change password (with old-token invalidation), expiring single-use
password reset (dev outbox, no enumeration, expiry, reuse), account deletion
(right to erasure), personal data export, plus the security controls added to
the app: hardening headers, the request body-size guard and login throttling.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, select

from app.api.routes import auth
from app.models import Bookmark, User
from app.models._mixins import utcnow
from app.services import email_service


# ---- helpers --------------------------------------------------------------
def _register(client, email="rakesh@example.com", password="supersecret123", name="Rakesh"):
    return client.post(
        "/api/auth/register", json={"name": name, "email": email, "password": password}
    )


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _token_from_last_reset_email():
    assert email_service.OUTBOX, "expected a captured reset email in the dev outbox"
    url = email_service.OUTBOX[-1]["url"]
    return parse_qs(urlparse(url).query)["token"][0]


# ---- change password ------------------------------------------------------
def test_change_password_rotates_and_invalidates_old_token(client):
    token = _register(client).json()["access_token"]
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200

    resp = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "supersecret123", "new_password": "brandnewpass9"},
    )
    assert resp.status_code == 204, resp.text
    # The pre-change token is now rejected.
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401
    # ...and the new password authenticates with a working token.
    login2 = _login(client, "rakesh@example.com", "brandnewpass9")
    assert login2.status_code == 200
    assert client.get("/api/auth/me", headers=_auth(login2.json()["access_token"])).status_code == 200


def test_change_password_rejects_wrong_current(client):
    token = _register(client).json()["access_token"]
    resp = client.post(
        "/api/auth/change-password",
        headers=_auth(token),
        json={"current_password": "wrongwrong1", "new_password": "brandnewpass9"},
    )
    assert resp.status_code == 403


def test_change_password_requires_auth(client):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "supersecret123", "new_password": "brandnewpass9"},
    )
    assert resp.status_code == 401


# ---- password reset -------------------------------------------------------
def test_password_reset_request_captures_email_without_leaking_token(client):
    _register(client)
    resp = client.post("/api/auth/password-reset/request", json={"email": "rakesh@example.com"})
    assert resp.status_code == 202
    assert email_service.OUTBOX and email_service.OUTBOX[-1]["to"] == "rakesh@example.com"
    # The HTTP body must never carry the token.
    assert "token" not in resp.text.lower()


def test_password_reset_request_unknown_email_is_indistinguishable(client):
    resp = client.post("/api/auth/password-reset/request", json={"email": "ghost@example.com"})
    assert resp.status_code == 202  # same status: no enumeration
    assert email_service.OUTBOX == []  # nothing emailed


def test_password_reset_confirm_flow_is_single_use(client):
    token = _register(client).json()["access_token"]
    client.post("/api/auth/password-reset/request", json={"email": "rakesh@example.com"})
    reset_token = _token_from_last_reset_email()

    conf = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "freshpass123"},
    )
    assert conf.status_code == 204
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401  # old token dead
    assert _login(client, "rakesh@example.com", "freshpass123").status_code == 200
    # Reuse of the consumed token now fails.
    again = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "anotherpass1"},
    )
    assert again.status_code == 400


def test_password_reset_confirm_rejects_bad_token(client):
    resp = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "freshpass123"},
    )
    assert resp.status_code == 400


def test_password_reset_confirm_rejects_expired_token(client, session):
    _register(client)
    client.post("/api/auth/password-reset/request", json={"email": "rakesh@example.com"})
    reset_token = _token_from_last_reset_email()
    user = session.scalar(select(User).where(User.email == "rakesh@example.com"))
    user.reset_expires_at = utcnow() - timedelta(minutes=5)
    session.commit()
    resp = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "freshpass123"},
    )
    assert resp.status_code == 400


# ---- account deletion -----------------------------------------------------
def test_delete_account_erases_owned_data(client, session):
    from app.models import Article

    reg = _register(client, email="bye@example.com")
    token, uid = reg.json()["access_token"], reg.json()["user"]["id"]

    article = Article(
        title="Seed", url="https://example.com/seed", provider="google_news",
        name_of_exam="", exam_category="", board="", conducted_by="", pbt_cbt="",
        state="", conducted_in="", category="", reason="", exam_year="",
    )
    session.add(article)
    session.commit()
    session.add(Bookmark(user_id=uid, article_id=article.id))
    session.commit()
    owned = select(func.count()).select_from(Bookmark).where(Bookmark.user_id == uid)
    assert session.scalar(owned) == 1

    assert client.delete("/api/auth/account", headers=_auth(token)).status_code == 204
    # Token now resolves to a deleted user.
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401
    # Owned data and the account itself are gone.
    assert session.scalar(owned) == 0
    assert session.get(User, uid) is None


# ---- personal data export -------------------------------------------------
def test_export_personal_data(seeded_client):
    c = seeded_client
    reg = _register(c, email="me@example.com")
    token = reg.json()["access_token"]
    aid = c.get("/api/articles").json()["items"][0]["id"]
    c.post("/api/bookmarks", json={"article_id": aid}, headers=_auth(token))
    c.post("/api/search", json={"query": "NEET"}, headers=_auth(token))

    resp = c.get("/api/auth/me/data", headers=_auth(token))
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    data = resp.json()
    assert data["profile"]["email"] == "me@example.com"
    assert data["counts"]["bookmarks"] == 1
    assert data["counts"]["searches"] >= 1
    assert data["bookmarks"][0]["url"]  # article metadata resolved


def test_export_requires_auth(client):
    assert client.get("/api/auth/me/data").status_code == 401


# ---- security controls ----------------------------------------------------
def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in resp.headers
    assert resp.headers["referrer-policy"] == "no-referrer"


def test_large_request_body_rejected(client):
    big = {"email": "a" * 1_200_000, "password": "x"}
    assert client.post("/api/auth/login", json=big).status_code == 413


def test_login_is_rate_limited(client, monkeypatch):
    _register(client)
    monkeypatch.setattr(auth.login_limiter, "max_attempts", 3)
    for _ in range(3):
        assert _login(client, "rakesh@example.com", "wrongwrong1").status_code == 401
    throttled = _login(client, "rakesh@example.com", "wrongwrong1")
    assert throttled.status_code == 429
    assert "retry-after" in throttled.headers


def test_successful_login_resets_failure_window(client, monkeypatch):
    _register(client)
    monkeypatch.setattr(auth.login_limiter, "max_attempts", 3)
    assert _login(client, "rakesh@example.com", "wrongwrong1").status_code == 401
    assert _login(client, "rakesh@example.com", "supersecret123").status_code == 200  # clears
    # Window was cleared, so a fresh wrong attempt is a 401, not a 429.
    assert _login(client, "rakesh@example.com", "wrongwrong1").status_code == 401
