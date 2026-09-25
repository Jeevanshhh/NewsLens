"""Engine / session management.

A small `Database` holder so tests can build an isolated engine (in-memory
SQLite) while the app uses a settings-driven default (SQLite in dev,
PostgreSQL in production). Sessions are supplied to FastAPI via `get_db`.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database.base import Base
from app.database import rls  # noqa: F401  (side-effect: registers the RLS after_begin listener)


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    kwargs = {}
    # A shared in-memory SQLite DB must reuse one connection across sessions.
    if url.startswith("sqlite") and (":memory:" in url or url == "sqlite://"):
        kwargs["poolclass"] = StaticPool
    return create_engine(url, connect_args=connect_args, future=True, **kwargs)


class Database:
    def __init__(self, url: str) -> None:
        # Import models so their tables register on Base.metadata before use.
        from app import models  # noqa: F401  (side-effect: table registration)

        self.url = url
        self.engine: Engine = make_engine(url)
        self.SessionLocal: sessionmaker[Session] = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
        )

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)


_db: Optional[Database] = None


def get_database() -> Database:
    """Lazily-initialised application-wide database (from settings)."""
    global _db
    if _db is None:
        _db = Database(get_settings().database_url)
    return _db


def init_db() -> None:
    get_database().create_all()


def get_db():
    """FastAPI dependency yielding a scoped session."""
    session = get_database().SessionLocal()
    try:
        yield session
    finally:
        session.close()
