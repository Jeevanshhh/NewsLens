"""Phase 12 - Auth tests: password/JWT primitives + register/login/me and
per-user scoping of bookmarks & search history. Fully offline."""
from __future__ import annotations

import jwt as pyjwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ---- security primitives (no HTTP) ---------------------------------------
def test_password_hash_roundtrip():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert "correct horse battery" not in stored  # plaintext never stored
    assert verify_password("correct horse battery", stored) is True
    assert verify_password("wrong password", stored) is False


def test_password_hash_uses_salt():
    # Same password -> different digests (random salt each time).
    assert hash_password("pw-12345678") != hash_password("pw-12345678")
    assert verify_password("pw-12345678", hash_password("pw-12345678")) is True


def test_verify_password_rejects_malformed():
    assert verify_password("x", "not-a-valid-digest") is False
    assert verify_password("x", None) is False
    assert verify_password("x", "") is False


def test_jwt_roundtrip_and_tamper():
    token = create_access_token(42, extra_claims={"email": "a@b.co"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "a@b.co"
    assert "exp" in payload and "iat" in payload
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token + "corrupt")


# ---- API helpers ----------------------------------------------------------
def _register(client, email="rakesh@example.com", password="supersecret123", name="Rakesh"):
    return client.post(
        "/api/auth/register", json={"name": name, "email": email, "password": password}
    )


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ---- register / login / me ------------------------------------------------
def test_register_returns_token_and_me_works(client):
    resp = _register(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "rakesh@example.com"

    me = client.get("/api/auth/me", headers=_auth_header(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "rakesh@example.com"


def test_register_duplicate_email_conflict(client):
    assert _register(client).status_code == 201
    dup = _register(client)
    assert dup.status_code == 409


def test_register_rejects_short_password(client):
    resp = _register(client, password="short")
    assert resp.status_code == 422


def test_register_rejects_invalid_email(client):
    resp = _register(client, email="not-an-email")
    assert resp.status_code == 422


def test_login_success(client):
    _register(client)
    resp = client.post(
        "/api/auth/login", json={"email": "rakesh@example.com", "password": "supersecret123"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    _register(client)
    resp = client.post(
        "/api/auth/login", json={"email": "rakesh@example.com", "password": "wrongwrong1"}
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "whatever12"}
    )
    assert resp.status_code == 401


def test_email_is_case_insensitive_normalized(client):
    assert _register(client, email="Mixed@Case.com").status_code == 201
    login = client.post(
        "/api/auth/login", json={"email": "mixed@case.com", "password": "supersecret123"}
    )
    assert login.status_code == 200


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_invalid_token(client):
    resp = client.get("/api/auth/me", headers=_auth_header("garbage.token.value"))
    assert resp.status_code == 401


# ---- per-user scoping -----------------------------------------------------
def test_bookmarks_scoped_per_user(seeded_client):
    c = seeded_client
    token = _register(c, email="owner@example.com").json()["access_token"]
    aid = c.get("/api/articles").json()["items"][0]["id"]

    # Bookmark as the authenticated user.
    created = c.post("/api/bookmarks", json={"article_id": aid}, headers=_auth_header(token))
    assert created.status_code == 201

    # Visible to that user, invisible to the anonymous scope.
    assert c.get("/api/bookmarks", headers=_auth_header(token)).json()["count"] == 1
    assert c.get("/api/bookmarks").json()["count"] == 0


def test_search_history_scoped_per_user(api_client):
    c = api_client
    token = _register(c, email="searcher@example.com").json()["access_token"]

    sid = c.post("/api/search", json={"query": "NEET"}, headers=_auth_header(token)).json()["search_id"]

    # Owned search shows in the user's history only.
    assert c.get("/api/searches", headers=_auth_header(token)).json()["count"] == 1
    assert c.get("/api/searches").json()["count"] == 0

    # Anonymous caller cannot delete someone else's search (no existence leak).
    assert c.delete(f"/api/searches/{sid}").status_code == 404
    # The owner can.
    assert c.delete(f"/api/searches/{sid}", headers=_auth_header(token)).status_code == 200
