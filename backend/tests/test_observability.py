"""Command 7 - Monitoring / observability tests. Offline."""
from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, request_id_var


def test_health_reports_provider_flags_without_secrets(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "providers" in body
    # No secret material is ever present.
    text = json.dumps(body)
    assert "secret" not in text.lower() and "password" not in text.lower()


def test_readiness_pings_the_database(client):
    resp = client.get("/api/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_request_id_is_minted_and_returned(client):
    resp = client.get("/api/health")
    assert resp.headers.get("x-request-id")


def test_inbound_request_id_is_propagated(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "trace-me-123"})
    assert resp.headers.get("x-request-id") == "trace-me-123"


def test_json_formatter_emits_parseable_records():
    record = logging.LogRecord("app.test", logging.WARNING, "path", 1, "hi %s", "there", None)
    token = request_id_var.set("req-xyz")
    try:
        record.request_id = request_id_var.get()
    finally:
        request_id_var.reset(token)

    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hi there"
    assert payload["level"] == "WARNING"
    assert payload["request_id"] == "req-xyz"
    assert "ts" in payload
