"""enforce RLS for the non-owner application role

Closes the Phase-11 P0: previously the tables had RLS *enabled* but not
*forced*, and the backend connected as the table owner - so PostgreSQL's owner
bypass meant the policies never actually constrained the application. This
revision turns RLS into a real defence-in-depth boundary for the user-owned /
user-linked activity tables (``bookmarks``, ``searches``, ``reports`` and the
``search_results`` junction):

* ``FORCE ROW LEVEL SECURITY`` so even a table-owner connection is bound.
* Replace the single ``tenant_isolation`` ``FOR ALL`` policy with explicit,
  per-command SELECT / INSERT / UPDATE / DELETE policies (writes also get a
  ``WITH CHECK`` so a row can never be created or moved to belong to someone
  else).
* Grant the runtime application role (a NON-owner, ``NOBYPASSRLS`` login named by
  ``RLS_APP_ROLE``, default ``newslens_app``) only the privileges the app needs.

The policy DDL is imported from :mod:`app.database.rls_sql` - the same module the
real-PostgreSQL integration test uses - so production and test can't drift.

It is a no-op on SQLite (development + the offline suite). It never touches
``articles``/``users`` RLS (those stay global/shared) and never deletes data.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-25 12:00:00.000000+00:00

"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

from app.database import rls_sql


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _app_role() -> str:
    """Name of the non-owner runtime role to grant privileges to.

    Configurable (not hard-coded) so it stays decoupled from any one deployment;
    the role itself is provisioned out-of-band (docker-entrypoint / ops runbook),
    never with a password baked into a migration.
    """
    return os.getenv("RLS_APP_ROLE", "newslens_app")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # RLS is PostgreSQL-only; inert on SQLite.

    bind = op.get_bind()
    for stmt in rls_sql.apply_rls():
        bind.exec_driver_sql(stmt)

    # Grant the runtime role only if it has been provisioned in this cluster.
    # Creating roles + passwords is an operator/infra step (kept out of source
    # control), so a missing role must not fail the migration.
    role = _app_role()
    exists = bind.execute(
        _pg_role_exists(), {"role": role}
    ).scalar()
    if exists:
        for stmt in rls_sql.grant_statements(role):
            bind.exec_driver_sql(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    bind = op.get_bind()
    for stmt in rls_sql.revert_rls():
        bind.exec_driver_sql(stmt)


def _pg_role_exists():
    """Parameterized existence probe for a cluster role (no interpolation)."""
    from sqlalchemy import text

    return text("SELECT 1 FROM pg_roles WHERE rolname = :role")
