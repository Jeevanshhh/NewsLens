"""Analytics API tests (Phase 8).

All expected numbers are derived by hand from the deterministic fake article
set in conftest - the service must reproduce exactly the stored data, never
invent figures.
"""
from __future__ import annotations


def _keys(distribution):
    return {entry["key"]: entry["count"] for entry in distribution}


def _register(client, email):
    resp = client.post(
        "/api/auth/register",
        json={"name": "Tester", "email": email, "password": "supersecret123"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_analytics_empty_db(client):
    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_articles"] == 0
    assert body["by_category"] == []
    assert body["timeline"] == []


def test_analytics_overview_counts(seeded_client):
    body = seeded_client.get("/api/analytics").json()
    assert body["total_articles"] == 3
    assert _keys(body["by_provider"]) == {"google_news": 3}
    assert _keys(body["by_category"]) == {"Paper Leak": 1, "Other": 2}
    assert _keys(body["by_state"]) == {"Maharashtra": 1, "Delhi": 1, "Unknown": 1}
    assert _keys(body["by_exam"]) == {"NEET UG": 2, "Unknown": 1}


def test_analytics_timeline(seeded_client):
    body = seeded_client.get("/api/analytics").json()
    dates = {entry["date"]: entry["count"] for entry in body["timeline"]}
    assert dates == {"2024-05-05": 1, "2024-05-06": 1, "2024-06-01": 1}


def test_analytics_provider_filter(seeded_client):
    body = seeded_client.get("/api/analytics", params={"provider": "google_news"}).json()
    assert body["total_articles"] == 3
    missing = seeded_client.get("/api/analytics", params={"provider": "newsdata"}).json()
    assert missing["total_articles"] == 0


def test_analytics_trend_with_change(seeded_client):
    body = seeded_client.get(
        "/api/analytics/trend",
        params={
            "current_from": "2024-06-01",
            "current_to": "2024-06-30",
            "previous_from": "2024-05-01",
            "previous_to": "2024-05-31",
        },
    ).json()
    assert body["current"] == 1
    assert body["previous"] == 2
    assert body["percentage_change"] == -50.0
    assert body["method"] == "article_count_by_published_date"


def test_analytics_trend_divide_by_zero(seeded_client):
    body = seeded_client.get(
        "/api/analytics/trend",
        params={
            "current_from": "2024-05-01",
            "current_to": "2024-05-31",
            "previous_from": "2023-01-01",
            "previous_to": "2023-01-31",
        },
    ).json()
    assert body["current"] == 2
    assert body["previous"] == 0
    assert body["percentage_change"] is None


# ---- personal metrics must be user-scoped (Phase 0 leak fix) -------------- #
def test_analytics_search_count_is_user_scoped(api_client):
    c = api_client
    tok_a = _register(c, "a@example.com")
    tok_b = _register(c, "b@example.com")

    # User A runs two searches, user B runs one.
    c.post("/api/search", json={"query": "NEET"}, headers=_auth(tok_a))
    c.post("/api/search", json={"query": "UPSC"}, headers=_auth(tok_a))
    c.post("/api/search", json={"query": "NEET"}, headers=_auth(tok_b))

    a = c.get("/api/analytics", headers=_auth(tok_a)).json()
    b = c.get("/api/analytics", headers=_auth(tok_b)).json()
    assert a["search_count"] == 2
    assert b["search_count"] == 1

    # The article corpus stays global/shared - not filtered per user.
    anon_total = c.get("/api/analytics").json()["total_articles"]
    assert a["total_articles"] == b["total_articles"] == anon_total


def test_analytics_bookmark_count_is_user_scoped(api_client):
    c = api_client
    tok_a = _register(c, "owner@example.com")
    c.post("/api/search", json={"query": "NEET"}, headers=_auth(tok_a))
    aid = c.get("/api/articles").json()["items"][0]["id"]
    assert c.post("/api/bookmarks", json={"article_id": aid}, headers=_auth(tok_a)).status_code == 201

    assert c.get("/api/analytics", headers=_auth(tok_a)).json()["bookmark_count"] == 1

    # A different user's personal count is isolated from the owner's.
    tok_b = _register(c, "other@example.com")
    assert c.get("/api/analytics", headers=_auth(tok_b)).json()["bookmark_count"] == 0
    # The anonymous scope must not observe the authenticated owner's bookmark.
    assert c.get("/api/analytics").json()["bookmark_count"] == 0
