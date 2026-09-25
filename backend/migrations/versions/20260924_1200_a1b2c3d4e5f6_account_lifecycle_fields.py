"""account lifecycle fields on users

Adds the columns the account-lifecycle + security flow needs:
``password_changed_at`` (token invalidation), and a single-use, expiring
password-reset token stored only as ``reset_token_hash`` + ``reset_expires_at``.

Revision ID: a1b2c3d4e5f6
Revises: 8e36985788d1
Create Date: 2026-09-24 12:00:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8e36985788d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table keeps this correct on SQLite (which cannot ALTER
    # multiple columns natively) while remaining a no-op wrapper on Postgres.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reset_token_hash", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reset_expires_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("reset_expires_at")
        batch_op.drop_column("reset_token_hash")
        batch_op.drop_column("password_changed_at")
