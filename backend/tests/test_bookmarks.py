"""Bookmarks + saved-searches tests (Phase 10).

Runs fully offline; reuses the seeded fixtures from conftest.
"""
from __future__ import annotations


def _first_article_id(client):
    items = client.get("/api/articles").json()["items"]
    return items[0]["id"]


def test_bookmark_then_list(seeded_client):
    aid = _first_article_id(seeded_client)
    resp = seeded_client.post("/api/bookmarks", json={"article_id": aid})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] is True
    assert body["bookmark"]["article"]["id"] == aid

    listing = seeded_client.get("/api/bookmarks").json()
    assert listing["count"] == 1
    assert listing["items"][0]["article_id"] == aid


def test_bookmark_is_idempotent(seeded_client):
    aid = _first_article_id(seeded_client)
    seeded_client.post("/api/bookmarks", json={"article_id": aid})
    second = seeded_client.post("/api/bookmarks", json={"article_id": aid})
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert seeded_client.get("/api/bookmarks").json()["count"] == 1


def test_bookmark_missing_article_404(seeded_client):
    resp = seeded_client.post("/api/bookmarks", json={"article_id": 987654})
    assert resp.status_code == 404


def test_remove_bookmark(seeded_client):
    aid = _first_article_id(seeded_client)
    seeded_client.post("/api/bookmarks", json={"article_id": aid})
    removed = seeded_client.delete(f"/api/bookmarks/{aid}")
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True
    # removing again -> 404
    assert seeded_client.delete(f"/api/bookmarks/{aid}").status_code == 404


def test_bookmark_status(seeded_client):
    items = seeded_client.get("/api/articles").json()["items"]
    a, b = items[0]["id"], items[1]["id"]
    seeded_client.post("/api/bookmarks", json={"article_id": a})
    status = seeded_client.get("/api/bookmarks/status", params={"ids": f"{a},{b}"}).json()["status"]
    assert status[str(a)] is True
    assert status[str(b)] is False


def test_bookmark_status_bad_ids(seeded_client):
    resp = seeded_client.get("/api/bookmarks/status", params={"ids": "1,abc"})
    assert resp.status_code == 422


def test_unsave_search(api_client):
    sid = api_client.post("/api/search", json={"query": "NEET"}).json()["search_id"]
    api_client.post(f"/api/searches/{sid}/save", params={"name": "keep"})
    assert api_client.get("/api/searches", params={"saved_only": True}).json()["count"] == 1
    unsaved = api_client.post(f"/api/searches/{sid}/unsave")
    assert unsaved.status_code == 200
    assert unsaved.json()["is_saved"] is False
    assert api_client.get("/api/searches", params={"saved_only": True}).json()["count"] == 0


def test_delete_search(api_client):
    sid = api_client.post("/api/search", json={"query": "NEET"}).json()["search_id"]
    assert api_client.get("/api/searches").json()["count"] == 1
    deleted = api_client.delete(f"/api/searches/{sid}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert api_client.get("/api/searches").json()["count"] == 0
    assert api_client.delete(f"/api/searches/{sid}").status_code == 404
