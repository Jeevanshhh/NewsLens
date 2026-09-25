"""Tests for the Phase 1 health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_index():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["health"] == "/api/health"


def test_health_returns_ok_and_no_secrets():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ok"
    assert body["version"]
    assert set(body["providers"].keys()) == {"google_news_rss", "gnews", "newsdata"}

    # Only booleans about provider config may be exposed, never key values.
    for value in body["providers"].values():
        assert isinstance(value, bool)

    # Guard against accidental secret leakage in the response payload.
    raw = resp.text.lower()
    assert "api_key" not in raw
    assert "secret" not in raw
