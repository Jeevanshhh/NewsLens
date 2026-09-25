"""Search + article API tests (Phase 5).

Runs entirely offline: the search route's collectors are replaced with fake
collectors (see conftest), so no network calls or API keys are involved.
"""
from __future__ import annotations


def test_search_returns_summary_and_dedups(api_client):
    resp = api_client.post(
        "/api/search",
        json={"query": "NEET", "sources": ["google_news", "gnews"], "max_results": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "NEET"
    assert body["total_collected"] == 6  # 3 articles x 2 providers
    assert body["unique_results"] == 3  # de-duplicated by URL
    assert body["new_stored"] == 3
    assert set(body["per_provider"]) == {"google_news", "gnews"}
    assert body["search_id"] >= 1


def test_search_blank_query_rejected(api_client):
    resp = api_client.post("/api/search", json={"query": "   "})
    assert resp.status_code == 422


def test_search_unknown_source_rejected(api_client):
    resp = api_client.post("/api/search", json={"query": "NEET", "sources": ["bing_news"]})
    assert resp.status_code == 422


def test_search_inverted_dates_rejected(api_client):
    resp = api_client.post(
        "/api/search",
        json={"query": "NEET", "from_date": "2024-06-01", "to_date": "2024-01-01"},
    )
    assert resp.status_code == 422


def test_articles_listed_after_search(seeded_client):
    resp = seeded_client.get("/api/articles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    titles = {item["title"] for item in body["items"]}
    assert any("NEET" in t for t in titles)


def test_article_filter_by_state(seeded_client):
    resp = seeded_client.get("/api/articles", params={"state": "Maharashtra"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["state"] == "Maharashtra"


def test_article_text_search_q(seeded_client):
    resp = seeded_client.get("/api/articles", params={"q": "protest"})
    body = resp.json()
    assert body["total"] == 1
    assert "protest" in body["items"][0]["title"].lower()


def test_article_detail_and_404(seeded_client):
    listed = seeded_client.get("/api/articles").json()["items"]
    some_id = listed[0]["id"]
    detail = seeded_client.get(f"/api/articles/{some_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == some_id
    missing = seeded_client.get("/api/articles/999999")
    assert missing.status_code == 404


def test_search_history_and_save(api_client):
    sid = api_client.post("/api/search", json={"query": "NEET"}).json()["search_id"]
    hist = api_client.get("/api/searches").json()
    assert hist["count"] == 1
    assert hist["items"][0]["id"] == sid
    assert hist["items"][0]["is_saved"] is False

    saved = api_client.post(f"/api/searches/{sid}/save", params={"name": "My NEET"})
    assert saved.status_code == 200
    assert saved.json()["is_saved"] is True

    saved_only = api_client.get("/api/searches", params={"saved_only": True}).json()
    assert saved_only["count"] == 1

    unsaved_only = api_client.post("/api/search", json={"query": "UPSC"}).json()
    # The new search is unsaved, so saved_only still returns just the one.
    assert api_client.get("/api/searches", params={"saved_only": True}).json()["count"] == 1
    assert unsaved_only["search_id"] != sid


def test_save_missing_search_404(api_client):
    resp = api_client.post("/api/searches/424242/save")
    assert resp.status_code == 404
