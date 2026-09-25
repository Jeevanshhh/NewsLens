"""Export endpoint tests (Phase 9): format, scoping and download headers."""
from __future__ import annotations


def test_export_csv(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment;" in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Title,Source,Provider")
    assert "https://example.com/neet-leak-maharashtra" in text
    # one header + three article rows
    assert len([ln for ln in text.splitlines() if ln.strip()]) == 4


def test_export_csv_respects_filter(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "csv", "state": "Delhi"})
    text = resp.content.decode("utf-8-sig")
    data_lines = [ln for ln in text.splitlines() if ln.strip()][1:]
    assert len(data_lines) == 1
    assert "Delhi" in data_lines[0]


def test_export_scoped_to_search(seeded_client):
    sid = seeded_client.get("/api/searches").json()["items"][0]["id"]
    resp = seeded_client.get("/api/export", params={"format": "csv", "search_id": sid})
    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")
    assert "neet-leak-maharashtra" in text


def test_export_xlsx(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "xlsx"})
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"  # zip container
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_pdf(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "pdf"})
    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"
    assert resp.headers["content-type"] == "application/pdf"


def test_export_docx(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "docx"})
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    assert "wordprocessingml" in resp.headers["content-type"]


def test_export_unsupported_format(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "rtf"})
    assert resp.status_code == 422


def test_export_unknown_search_404(seeded_client):
    resp = seeded_client.get("/api/export", params={"format": "csv", "search_id": 99999})
    assert resp.status_code == 404


def test_export_empty_result_still_works(client):
    resp = client.get("/api/export", params={"format": "csv"})
    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")
    # header row only, no data rows
    assert [ln for ln in text.splitlines() if ln.strip()][1:] == []
