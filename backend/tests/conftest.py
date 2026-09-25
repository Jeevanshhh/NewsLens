"""Shared pytest fixtures: isolated in-memory DB + FastAPI TestClient."""
from __future__ import annotations

import os

# Ensure the app boots against an in-memory DB during tests (before any
# settings are cached) so the lifespan's init_db() never touches a real file.
os.environ["DATABASE_URL"] = "sqlite://"

# Keep the offline tests fully deterministic and network-free: the supervised
# topic model is exercised directly in test_news_topics.py, but the seeded
# search route below must stay stable (exact analytics category counts).
os.environ["ENABLE_TOPIC_MODEL"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401  register tables
from app.api.deps import get_collectors
from app.core.config import get_settings
from app.database import connection
from app.database.base import Base
from app.database.connection import get_db, make_engine
from app.main import app
from app.schemas.article import Article

# Reset any caches imported above so the in-memory URL takes effect.
get_settings.cache_clear()
connection._db = None


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Isolate process-global, stateful singletons between tests.

    The login throttle and the e-mail outbox are module-level objects shared
    across the whole suite; without this, failed-login attempts in one test
    would bleed into another and captured reset e-mails would pile up.
    """
    from app.api.routes import auth
    from app.services import email_service

    auth.login_limiter.reset()
    email_service.clear_outbox()
    yield
    auth.login_limiter.reset()
    email_service.clear_outbox()


@pytest.fixture
def engine():
    eng = make_engine("sqlite://")  # in-memory, StaticPool (see make_engine)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    sess = TestSession()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def client(session) -> TestClient:
    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- Offline fake collectors (no network, no API keys) ---------------------
# Each provider returns the SAME set of raw articles, so a multi-source search
# exercises the pipeline's URL-based de-duplication.
FAKE_ARTICLES = [
    Article(
        title="NEET UG paper leak sparks students protest in Maharashtra",
        description="Students demanded a CBI probe after the question paper leak.",
        url="https://example.com/neet-leak-maharashtra",
        source="The Hindu",
        provider="google_news",
        published_at="2024-05-05T09:00:00Z",
        language="en",
        country="in",
    ),
    Article(
        title="NEET UG 2024 CBT exam to be conducted in Delhi by NTA",
        description="The National Testing Agency announced the schedule in Delhi.",
        url="https://example.com/neet-cbt-delhi",
        source="Times of India",
        provider="google_news",
        published_at="2024-05-06T12:00:00Z",
        language="en",
        country="in",
    ),
    Article(
        title="UPSC Civil Services final results declared",
        description="The Union Public Service Commission released the list.",
        url="https://example.com/upsc-results",
        source="Indian Express",
        provider="google_news",
        published_at="2024-06-01T18:30:00Z",
        language="en",
        country="in",
    ),
]


def _fake_collectors() -> dict:
    def collect(ctx):
        # Re-tag provider so per-provider attribution is observable downstream.
        return [a.model_copy(update={"provider": a.provider}) for a in FAKE_ARTICLES]

    return {"google_news": collect, "gnews": collect, "newsdata": collect}


@pytest.fixture
def api_client(client) -> TestClient:
    """TestClient with offline fake collectors wired into the search route."""
    app.dependency_overrides[get_collectors] = _fake_collectors
    yield client


@pytest.fixture
def seeded_client(api_client) -> TestClient:
    """Run one search so the DB holds articles, then hand back the client."""
    resp = api_client.post(
        "/api/search",
        json={"query": "NEET", "sources": ["google_news", "gnews"], "max_results": 10},
    )
    assert resp.status_code == 200, resp.text
    return api_client
