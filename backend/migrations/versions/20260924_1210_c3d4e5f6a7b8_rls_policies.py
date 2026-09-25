"""row level security for user-owned tables

Enables PostgreSQL Row-Level Security on the user-owned activity tables
(``bookmarks``, ``searches``, ``reports``) with a per-user isolation policy keyed
on the transaction-local setting ``app.current_user_id`` (applied by
:mod:`app.database.rls`). An unset value falls back to the anonymous scope
(``user_id IS NULL``), matching the application's own ``WHERE user_id`` scoping.

This is **defence-in-depth** for Postgres/Supabase deployments - chiefly for the
non-owner client roles (e.g. Supabase ``anon`` / ``authenticated``). It is a
no-op on SQLite. It deliberately does NOT add ``FORCE ROW LEVEL SECURITY``, so a
trusted backend that owns the tables keeps working unchanged; add FORCE (and run
the backend as a non-owner role) to have RLS constrain the backend too.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-24 12:10:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNED_TABLES = ("bookmarks", "searches", "reports")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # RLS is PostgreSQL-only; inert on SQLite.

    for table in _OWNED_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation" ON "{table}";')
        op.execute(
            f'''
            CREATE POLICY "tenant_isolation" ON "{table}"
              FOR ALL
              USING (
                COALESCE(NULLIF(current_setting('app.current_user_id', true), ''), '0')::int
                  = COALESCE(user_id, 0)
              )
              WITH CHECK (
                COALESCE(NULLIF(current_setting('app.current_user_id', true), ''), '0')::int
                  = COALESCE(user_id, 0)
              );
            '''
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _OWNED_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation" ON "{table}";')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')
