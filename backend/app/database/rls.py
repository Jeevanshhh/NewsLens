"""Row-Level-Security (RLS) session wiring for PostgreSQL / Supabase.

The companion migration (``migrations/versions/..._rls_policies.py``) enables
RLS on the user-owned tables (``bookmarks``, ``searches``, ``reports``) with
policies keyed on the PostgreSQL setting ``app.current_user_id``.

This module applies that setting:

* :func:`set_rls_user` stashes the acting user id on the session.
* An ``after_begin`` event re-asserts it as a *transaction-local* setting at the
  start of every transaction, so it never leaks across pooled connections and
  an unset id correctly falls back to the anonymous (``user_id IS NULL``) scope.

Everything is a no-op on SQLite (development + the offline test-suite): the
effective, test-covered isolation there and in the current deployment is the
explicit ``WHERE user_id = :me`` scoping in the services. RLS is *defence in
depth* for a Postgres deployment. The companion revision
``..._enforce_rls_app_role.py`` sets ``FORCE ROW LEVEL SECURITY`` and the
runtime connects as a non-owner ``NOBYPASSRLS`` role, so these policies now bind
the application too (not just third-party client roles). The real enforcement is
verified against an actual PostgreSQL instance in
``tests/test_postgres_rls_enforcement.py`` (skipped automatically when no
PostgreSQL test URL is configured).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


def set_rls_user(session: Session, user_id: Optional[int]) -> None:
    """Record the acting user so the next transaction sets the RLS variable.

    ``None`` means the anonymous scope. Call this before the session's first
    query in a request (the auth dependency does it from the JWT subject).
    """
    session.info["app_user_id"] = user_id


@event.listens_for(Session, "after_begin")
def _apply_rls_variable(session: Session, transaction, connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return  # SQLite / other backends: RLS wiring is inert.
    user_id = session.info.get("app_user_id")
    value = str(user_id) if user_id is not None else ""
    # Transaction-local (third arg TRUE) => cleared automatically at commit.
    connection.exec_driver_sql(
        "SELECT set_config('app.current_user_id', %s, TRUE)", (value,)
    )
