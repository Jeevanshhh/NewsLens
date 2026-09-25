"""Phase 2 tests: news collectors (fully mocked - no network, no real keys)."""
from __future__ import annotations

import types

import pytest
import requests

from app.schemas.article import Article
from app.services.news import base, gnews, google_news, newsdata
from app.services.news.base import SearchContext, first_str, http_get_json


class FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def capture(monkeypatch):
    """Patch base.requests.get; records (url, params) and returns a queued response."""
    calls: list[tuple[str, dict]] = []
    holder: dict[str, object] = {"response": FakeResponse(200, {}), "raises": None}

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if holder["raises"] is not None:
            raise holder["raises"]
        return holder["response"]

    monkeypatch.setattr(base.requests, "get", fake_get)
    return types.SimpleNamespace(calls=calls, holder=holder)


# --------------------------------------------------------------------------- #
# Google News RSS
# --------------------------------------------------------------------------- #
def test_google_news_maps_entries_and_date_operators(monkeypatch):
    entries = [
        {
            "title": "Students protest NEET",
            "summary": "Desc one",
            "link": "https://ex/1",
            "published": "Mon, 18 Aug 2026 10:00:00 GMT",
            "source": {"title": "NDTV"},
            "author": "Reporter",
        },
        {"title": "Second", "link": "https://ex/2"},
        {"title": "Third", "link": "https://ex/3"},
    ]
    captured: dict[str, str] = {}

    def fake_parse(url):
        captured["url"] = url
        return types.SimpleNamespace(entries=entries)

    monkeypatch.setattr(google_news.feedparser, "parse", fake_parse)

    ctx = SearchContext(
        query="NEET protest", from_date="2026-06-01", to_date="2026-08-31", max_results=2
    )
    articles = google_news.collect(ctx, rss_language="en-IN", rss_country="IN")

    # max_results caps entries
    assert len(articles) == 2
    a0 = articles[0]
    assert isinstance(a0, Article)
    assert a0.provider == "google_news"
    assert a0.source == "NDTV"
    assert a0.description == "Desc one"
    assert a0.url == "https://ex/1"
    assert a0.keyword_matched == "NEET protest"
    # second entry has no summary/author -> None, never fabricated
    assert articles[1].description is None
    assert articles[1].source is None
    # date operators + locale are encoded into the RSS query
    assert "after%3A2026-06-01" in captured["url"]
    assert "before%3A2026-08-31" in captured["url"]
    assert "hl=en-IN" in captured["url"]
    assert "gl=IN" in captured["url"]


def test_google_news_parse_failure_returns_empty(monkeypatch):
    def boom(_url):
        raise RuntimeError("feed down")

    monkeypatch.setattr(google_news.feedparser, "parse", boom)
    ctx = SearchContext(query="anything")
    assert google_news.collect(ctx) == []


# --------------------------------------------------------------------------- #
# GNews
# --------------------------------------------------------------------------- #
def test_gnews_maps_articles_and_params(capture):
    capture.holder["response"] = FakeResponse(
        200,
        {
            "articles": [
                {
                    "title": "T1",
                    "description": "D1",
                    "url": "U1",
                    "publishedAt": "2026-08-18T00:00:00Z",
                    "source": {"name": "The Hindu"},
                    "image": "img1",
                    "author": "Alice",
                }
            ]
        },
    )
    ctx = SearchContext(query="NEET scam", from_date="2026-06-01", to_date="2026-08-31")
    articles = gnews.collect(ctx, api_key="dummy-key")

    assert len(articles) == 1
    a = articles[0]
    assert a.provider == "gnews"
    assert a.source == "The Hindu"
    assert a.image_url == "img1"
    assert a.published_at == "2026-08-18T00:00:00Z"

    url, params = capture.calls[0]
    assert url == gnews.ENDPOINT
    assert params["token"] == "dummy-key"
    assert params["q"] == "NEET scam"
    assert params["from"] == "2026-06-01T00:00:00Z"
    assert params["to"] == "2026-08-31T23:59:59Z"


def test_gnews_without_key_skips(capture):
    assert gnews.collect(SearchContext(query="x"), api_key=None) == []
    assert capture.calls == []  # no HTTP call attempted


def test_gnews_non_200_returns_empty(capture):
    capture.holder["response"] = FakeResponse(401, {"message": "invalid"})
    assert gnews.collect(SearchContext(query="x"), api_key="k") == []


# --------------------------------------------------------------------------- #
# NewsData
# --------------------------------------------------------------------------- #
def test_newsdata_maps_and_caps_size(capture):
    capture.holder["response"] = FakeResponse(
        200,
        {
            "status": "success",
            "results": [
                {
                    "title": "N1",
                    "description": "ND1",
                    "url": "NU1",
                    "pubDate": "2026-08-01T05:00:00Z",
                    "source_id": "thehindu",
                    "author": ["Bob"],
                    "image": "nimg",
                    "language": "en",
                    "country": "in",
                },
                {"title": "N2", "url": "NU2"},
                {"title": "N3", "url": "NU3"},
            ],
        },
    )
    ctx = SearchContext(query="NTA protest", max_results=2)
    articles = newsdata.collect(ctx, api_key="pk")

    assert len(articles) == 2
    a = articles[0]
    assert a.provider == "newsdata"
    assert a.source == "thehindu"
    assert a.author == "Bob"  # single-element list coerced
    assert a.image_url == "nimg"
    url, params = capture.calls[0]
    assert url == newsdata.ENDPOINT
    assert params["apikey"] == "pk"
    assert params["size"] == 2


def test_newsdata_without_key_skips(capture):
    assert newsdata.collect(SearchContext(query="x"), api_key="") == []
    assert capture.calls == []


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def test_http_get_json_network_error_returns_none(capture):
    capture.holder["raises"] = requests.ConnectionError("boom")
    assert http_get_json("http://x", {}) is None


def test_http_get_json_non_json_returns_none(capture):
    capture.holder["response"] = FakeResponse(200, raise_json=True)
    assert http_get_json("http://x", {}) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("abc", "abc"),
        ("", None),
        (["x", "y"], "x"),
        ([], None),
        ([None, "z"], "z"),
        (123, "123"),
    ],
)
def test_first_str(value, expected):
    assert first_str(value) == expected
