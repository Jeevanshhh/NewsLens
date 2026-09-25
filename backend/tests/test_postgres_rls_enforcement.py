"""REAL PostgreSQL Row-Level-Security enforcement tests (Phase-11 P0).

Unlike ``test_postgres_rls.py`` (which documents that SQLite can only verify
*application-layer* ``WHERE user_id`` scoping), these tests run against a live
PostgreSQL server and prove the database-level RLS boundary actually holds:

* tables are ``FORCE ROW LEVEL SECURITY``-bound,
* the acting role is a NON-owner with ``NOBYPASSRLS`` (exactly how the runtime
  backend connects after the P0 fix),
* isolation is established through the real :func:`app.database.rls.set_rls_user`
  + ``after_begin`` wiring (not a hand-rolled ``SET``), so we test the mechanism
  that ships.

Setup (per module):
1. Connect to the server as an admin (``NEWSELENS_PG_TEST_URL``).
2. Create a throwaway database + a non-owner runtime role.
3. Run the full Alembic migration chain as the admin/owner - which applies the
   schema AND the enforcement revision ``d4e5f6a7b8c9`` (FORCE + per-command
   policies + grants to the runtime role).
4. Seed rows for two users, then exercise the allow/deny matrix as the runtime
   role. Teardown drops the database and role.

If ``NEWSELENS_PG_TEST_URL`` is unset or the server is unreachable the whole
module SKIPS - it never fakes PostgreSQL behaviour on SQLite.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app import models  # register tables on Base.metadata
from app.database import rls
from app.models import Article, Bookmark, Report, Search, User, search_results

ADMIN_URL_ENV = "NEWSELENS_PG_TEST_URL"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _render(url) -> str:
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def pg_env():
    """Provision a fresh PostgreSQL DB + non-owner role, migrate, yield handles."""
    admin_raw = os.getenv(ADMIN_URL_ENV)
    if not admin_raw:
        pytest.skip(
            f"{ADMIN_URL_ENV} not set - real PostgreSQL RLS verification needs a "
            "live server. See tests/README_postgres_rls.md for the one-command setup."
        )

    admin = make_url(admin_raw)
    suffix = uuid.uuid4().hex[:8]
    test_db = f"newslens_rls_{suffix}"
    app_role = f"rls_app_{suffix}"
    app_pw = f"pw_{suffix}_x9"  # alnum/underscore only, safe in URLs
    owner_pw = f"pw_{suffix}_o9"
    owner_role = f"rls_owner_{suffix}"

    # Generous connect timeout: on a loaded local server, backend startup can
    # make authentication take longer than the default short timeouts allow.
    _CONN = {"connect_timeout": 90}
    maint = create_engine(_render(admin), isolation_level="AUTOCOMMIT", future=True,
                          connect_args=_CONN, pool_timeout=15)
    try:
        with maint.connect() as c:
            # A dedicated owner role (owns the schema/tables) and a separate
            # non-owner runtime role - mirroring the production split. The owner
            # role is NOT a superuser; the runtime role is NOINHERIT NOBYPASSRLS,
            # exactly like the backend's connection after the P0 fix. Passwords
            # here are internally generated alnum tokens (safe as SQL literals).
            c.execute(text(
                f"CREATE ROLE \"{owner_role}\" LOGIN PASSWORD '{owner_pw}' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
            ))
            c.execute(text(
                f"CREATE ROLE \"{app_role}\" LOGIN PASSWORD '{app_pw}' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
            ))
            c.execute(text(f'CREATE DATABASE "{test_db}" OWNER "{owner_role}"'))
    finally:
        maint.dispose()

    owner_url = admin.set(database=test_db, username=owner_role, password=owner_pw)
    app_url = admin.set(database=test_db, username=app_role, password=app_pw)
    # Superuser handle for the test DB: used for SEEDING and cross-user id
    # lookups. FORCE ROW LEVEL SECURITY also binds the *table owner*, so the
    # only role that can insert rows outside any user context is the admin
    # superuser (which bypasses RLS by definition).
    seed_url = admin.set(database=test_db)

    # Run the real migration chain as the owner, targeting the runtime role for
    # grants (exactly how docker-compose runs `alembic upgrade head` before boot).
    saved = {k: os.environ.get(k) for k in
             ("ALEMBIC_DATABASE_URL", "RLS_APP_ROLE")}
    os.environ["ALEMBIC_DATABASE_URL"] = _render(owner_url)
    os.environ["RLS_APP_ROLE"] = app_role
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
        command.upgrade(cfg, "head")

        seed_engine = create_engine(_render(seed_url), future=True,
                                    pool_pre_ping=True, connect_args=_CONN, pool_timeout=15)
        # pool_size=1 forces the SAME physical connection to be reused across
        # sessions - what the pooling-leak regression test relies on.
        app_engine = create_engine(
            _render(app_url), future=True, pool_size=1, max_overflow=0,
            pool_pre_ping=True, connect_args=_CONN, pool_timeout=15,
        )
        # Confirm we really are a non-owner that cannot bypass RLS.
        with app_engine.connect() as probe:
            bypass = probe.execute(text(
                "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )).scalar()
            is_owner = probe.execute(text(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            )).scalar()
        assert bypass is False and is_owner is False

        yield {
            "seed": sessionmaker(bind=seed_engine, autoflush=False,
                                 expire_on_commit=False, future=True),
            "app": sessionmaker(bind=app_engine, autoflush=False,
                                expire_on_commit=False, future=True),
            "app_engine": app_engine,
            "app_role": app_role,
        }
        seed_engine.dispose()
        app_engine.dispose()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        drop = create_engine(_render(admin), isolation_level="AUTOCOMMIT", future=True,
                             connect_args=_CONN, pool_timeout=15)
        try:
            with drop.connect() as c:
                c.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
                c.execute(text(f'DROP ROLE IF EXISTS "{app_role}"'))
                c.execute(text(f'DROP ROLE IF EXISTS "{owner_role}"'))
        finally:
            drop.dispose()


def _app_session(pg_env, user_id):
    """A session as the runtime role with ``app.current_user_id`` established by
    the *real* application wiring (rls.set_rls_user + after_begin)."""
    sess = pg_env["app"]()
    rls.set_rls_user(sess, user_id)
    return sess


@pytest.fixture()
def seeded(pg_env):
    """Create 2 articles, users A & B, and each user's owned rows (as the admin
    superuser, which bypasses RLS - the table owner role can NOT do this once
    FORCE ROW LEVEL SECURITY is applied)."""
    seed = pg_env["seed"]()
    art = Article(title="NEET UG paper leak protest", url=f"https://ex/{uuid.uuid4().hex}",
                  provider="google_news")
    art2 = Article(title="UPSC results declared", url=f"https://ex/{uuid.uuid4().hex}",
                   provider="gnews")
    a = User(name="Alice", email=f"a{uuid.uuid4().hex}@ex.com")
    b = User(name="Bob", email=f"b{uuid.uuid4().hex}@ex.com")
    seed.add_all([art, art2, a, b])
    seed.flush()
    seed.add(Bookmark(user_id=a.id, article_id=art.id))
    seed.add(Bookmark(user_id=b.id, article_id=art.id))
    seed.add(Search(user_id=a.id, query="NEET", is_saved=1, name="A saved"))
    seed.add(Search(user_id=b.id, query="UPSC", is_saved=1, name="B saved"))
    seed.add(Report(user_id=a.id, name="A report", type="csv", parameters={}))
    seed.add(Report(user_id=b.id, name="B report", type="csv", parameters={}))
    seed.commit()
    ids = {"article": art.id, "article2": art2.id, "a": a.id, "b": b.id}
    seed.close()
    return ids


# ---- positive: a user can fully manage their OWN data ----------------------
def test_user_selects_only_own_bookmarks(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        rows = s.scalars(select(Bookmark)).all()
        assert {r.user_id for r in rows} == {seeded["a"]}


def test_user_selects_own_saved_search_and_history(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        searches = s.scalars(select(Search)).all()
        assert len(searches) == 1 and searches[0].user_id == seeded["a"]


def test_user_selects_own_reports(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        reports = s.scalars(select(Report)).all()
        assert {r.user_id for r in reports} == {seeded["a"]}


def test_user_can_insert_own_bookmark(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        before = s.scalar(select(func.count()).select_from(Bookmark)
                          .where(Bookmark.user_id == seeded["a"]))
        s.add(Bookmark(user_id=seeded["a"], article_id=seeded["article2"]))
        s.commit()
        after = s.scalar(select(func.count()).select_from(Bookmark)
                         .where(Bookmark.user_id == seeded["a"]))
        assert after == before + 1


def test_user_can_update_own_record(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        own = s.scalars(select(Search).where(Search.user_id == seeded["a"])).first()
        own.name = "renamed by owner"
        s.commit()
        assert s.scalar(select(Search.name).where(Search.id == own.id)) == "renamed by owner"


def test_user_can_delete_own_record(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        own = s.scalars(select(Bookmark).where(Bookmark.user_id == seeded["a"])).first()
        s.delete(own)
        s.commit()
        assert s.get(Bookmark, own.id) is None


# ---- negative: cross-user access is DENIED by the database ----------------
def test_user_cannot_see_other_users_bookmark(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        b_rows = s.scalars(select(Bookmark).where(Bookmark.user_id == seeded["b"])).all()
        assert b_rows == []  # invisible under RLS even though we ask by owner id


def test_user_cannot_update_other_users_record(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        b_id = (pg_env["seed"]()
                .scalar(select(Search.id).where(Search.user_id == seeded["b"])))
        result = s.execute(
            text("UPDATE searches SET name = 'hijacked' WHERE id = :id"), {"id": b_id}
        )
        s.commit()
        assert result.rowcount == 0  # no B row is visible/updatable as A


def test_user_cannot_delete_other_users_record(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        b_id = (pg_env["seed"]()
                .scalar(select(Bookmark.id).where(Bookmark.user_id == seeded["b"])))
        result = s.execute(
            text("DELETE FROM bookmarks WHERE id = :id"), {"id": b_id}
        )
        s.commit()
        assert result.rowcount == 0


def test_user_cannot_insert_row_for_another_user(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        s.add(Bookmark(user_id=seeded["b"], article_id=seeded["article2"]))
        with pytest.raises(DBAPIError):  # WITH CHECK violation -> RLS error
            s.flush()
        s.rollback()


# ---- no authenticated context -> only the anonymous scope is visible ------
def test_anonymous_context_sees_no_tenant_rows(pg_env, seeded):
    with _app_session(pg_env, None) as s:
        assert s.scalars(select(Bookmark)).all() == []
        assert s.scalars(select(Search)).all() == []


# ---- transaction-local identity must not leak across pooled connections ---
def test_identity_is_transaction_local_on_pooled_connection(pg_env, seeded):
    """Same physical connection (pool_size=1): after A's transaction commits, a
    fresh session must NOT inherit A's identity - it falls back to anonymous."""
    with _app_session(pg_env, seeded["a"]) as s:
        assert s.scalars(select(Bookmark)).all() != []  # A context works
    # A brand-new session -> reuses the pooled connection, no user set.
    with _app_session(pg_env, None) as s:
        assert s.scalars(select(Bookmark)).all() == []  # A's rows no longer visible


def test_set_local_clears_at_commit(pg_env, seeded):
    """Low-level proof that set_config(..., is_local=TRUE) reverts at COMMIT, so
    a recycled connection can never carry a stale app.current_user_id."""
    a_id = seeded["a"]
    with pg_env["app_engine"].connect() as conn:
        with conn.begin():
            conn.exec_driver_sql("SELECT set_config('app.current_user_id', %s, TRUE)", (str(a_id),))
            assert conn.scalar(text(
                "SELECT current_setting('app.current_user_id', true)")) == str(a_id)
        # Transaction closed; the LOCAL setting is gone on the same connection.
        assert conn.scalar(text(
            "SELECT current_setting('app.current_user_id', true)")) in ("", None)


# ---- rollback must not persist ---------------------------------------------
def test_rolled_back_insert_is_not_persisted(pg_env, seeded):
    with _app_session(pg_env, seeded["a"]) as s:
        before = s.scalar(select(func.count()).select_from(Bookmark)
                          .where(Bookmark.user_id == seeded["a"]))
        s.add(Bookmark(user_id=seeded["a"], article_id=seeded["article2"]))
        s.flush()  # valid under A's context, but not committed
        s.rollback()
        after = s.scalar(select(func.count()).select_from(Bookmark)
                         .where(Bookmark.user_id == seeded["a"]))
        assert after == before


# ---- junction table (search_results) protected via owning search -----------
def test_search_results_isolated_through_owning_search(pg_env, seeded):
    # Superuser links each user's search to the article (bypasses RLS).
    seed = pg_env["seed"]()
    s_a = seed.scalar(select(Search.id).where(Search.user_id == seeded["a"]))
    s_b = seed.scalar(select(Search.id).where(Search.user_id == seeded["b"]))
    art = seeded["article"]
    seed.execute(search_results.insert(), [{"search_id": s_a, "article_id": art},
                                           {"search_id": s_b, "article_id": art}])
    seed.commit()
    seed.close()
    with _app_session(pg_env, seeded["a"]) as s:
        visible = s.execute(text(
            "SELECT search_id FROM search_results ORDER BY search_id")).scalars().all()
        assert visible == [s_a]  # only A's search linkage is reachable
