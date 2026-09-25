"""Command 8 - PostgreSQL/RLS support + per-user isolation tests.

RLS itself only exists on PostgreSQL, so it cannot be exercised by the offline
SQLite suite. What we CAN - and do - verify here is the effective isolation the
application enforces today (per-user ``WHERE user_id`` scoping), that the Postgres
detection helper works, and that the RLS session wiring is inert on SQLite.

These are *application-layer* isolation tests (kept intentionally - see Phase-11
§8: RLS is defence-in-depth, not a replacement for app authorization). The
DATABASE-level RLS boundary is verified separately, against a real PostgreSQL
server, in ``test_postgres_rls_enforcement.py``.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.core.config import Settings
from app.database import rls
from app.models import User


def _register(client, email, password="supersecret123", name="Tester"):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---- config + wiring helpers ---------------------------------------------
def test_is_postgres_detection():
    assert Settings(database_url="sqlite:///./x.db").is_postgres is False
    assert Settings(database_url="postgresql+psycopg://u@h/db").is_postgres is True
    assert Settings(database_url="postgres://u@h/db").is_postgres is True


def test_rls_setter_is_inert_on_sqlite(session):
    rls.set_rls_user(session, 5)
    assert session.info["app_user_id"] == 5
    # The after_begin hook returns early on SQLite; a query must just work.
    assert session.scalar(select(func.count()).select_from(User)) == 0


# ---- effective application-layer isolation -------------------------------
def test_saved_searches_are_isolated_between_users(seeded_client):
    c = seeded_client
    ta = _register(c, "a@example.com").json()["access_token"]
    tb = _register(c, "b@example.com").json()["access_token"]

    sa = c.post("/api/search", json={"query": "NEET"}, headers=_auth(ta)).json()["search_id"]
    c.post(f"/api/searches/{sa}/save", params={"name": "My NEET"}, headers=_auth(ta))

    # B sees nothing of A's, and cannot even confirm A's search exists (404).
    assert c.get("/api/searches", headers=_auth(tb)).json()["count"] == 0
    assert c.delete(f"/api/searches/{sa}", headers=_auth(tb)).status_code == 404
    # A sees their own.
    assert c.get("/api/searches", headers=_auth(ta)).json()["count"] == 1


def test_data_export_only_contains_the_owners_rows(seeded_client):
    c = seeded_client
    ta = _register(c, "a@example.com").json()["access_token"]
    tb = _register(c, "b@example.com").json()["access_token"]

    aid = c.get("/api/articles").json()["items"][0]["id"]
    c.post("/api/bookmarks", json={"article_id": aid}, headers=_auth(ta))
    c.post("/api/search", json={"query": "NEET"}, headers=_auth(ta))

    b_data = c.get("/api/auth/me/data", headers=_auth(tb)).json()
    assert b_data["counts"]["bookmarks"] == 0
    assert b_data["counts"]["searches"] == 0

    a_data = c.get("/api/auth/me/data", headers=_auth(ta)).json()
    assert a_data["counts"]["bookmarks"] == 1
    assert a_data["counts"]["searches"] >= 1


def test_bookmarks_are_isolated_between_users(seeded_client):
    c = seeded_client
    ta = _register(c, "a@example.com").json()["access_token"]
    tb = _register(c, "b@example.com").json()["access_token"]

    aid = c.get("/api/articles").json()["items"][0]["id"]
    assert c.post("/api/bookmarks", json={"article_id": aid}, headers=_auth(ta)).status_code == 201

    assert c.get("/api/bookmarks", headers=_auth(ta)).json()["count"] == 1
    assert c.get("/api/bookmarks", headers=_auth(tb)).json()["count"] == 0
