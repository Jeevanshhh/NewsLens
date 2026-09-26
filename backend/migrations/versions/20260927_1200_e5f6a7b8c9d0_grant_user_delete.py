"""grant DELETE on users to the runtime role (account deletion / right to erasure)

Closes the account-deletion defect: revision ``d4e5f6a7b8c9`` granted the
non-owner runtime role ``SELECT, INSERT, UPDATE`` on the ``users`` table but not
``DELETE``, so ``user_service.delete_account()``'s final ``DELETE FROM users``
raised a permission error (surfacing as a 500). ``users`` stays global / NOT
under RLS (auth must read it before any subject exists); only the privilege is
widened here.

Because ``d4e5f6a7b8c9`` has already run in production and Alembic never
re-applies an already-applied revision, the corrected grant ships as a *new*
forward revision that re-runs the (single source of truth) grant statements from
:mod:`app.database.rls_sql`. It is idempotent and a no-op on SQLite, and only
touches grants when the runtime role actually exists in the cluster (creating
roles + passwords remains an out-of-band operator step).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-27 12:00:00.000000+00:00

"""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

from app.database import rls_sql


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _app_role() -> str:
    """Name of the non-owner runtime role to (re)grant privileges to."""
    return os.getenv("RLS_APP_ROLE", "newslens_app")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # grants are PostgreSQL-only; inert on SQLite.

    bind = op.get_bind()
    role = _app_role()
    exists = bind.execute(_pg_role_exists(), {"role": role}).scalar()
    if exists:
        # Re-apply the full grant set (now including DELETE ON users). GRANT is
        # idempotent, so this only widens privileges - it never revokes.
        for stmt in rls_sql.grant_statements(role):
            bind.exec_driver_sql(stmt)


def downgrade() -> None:
    # Privileges are additive and harmless to leave in place; intentionally no-op
    # so a downgrade never re-breaks an application that legitimately needs them.
    return None


def _pg_role_exists():
    """Parameterized existence probe for a cluster role (no interpolation)."""
    from sqlalchemy import text

    return text("SELECT 1 FROM pg_roles WHERE rolname = :role")
