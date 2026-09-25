"""Alembic migration environment.

Reads the database URL from the application settings (which in turn come from
the environment / `.env`), so credentials are never stored in alembic.ini.
Autogeneration targets the ORM models' metadata.
"""
from __future__ import annotations

from logging.config import fileConfig

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app import models  # noqa: F401  ensure all tables register on Base.metadata
from app.database.base import Base

config = context.config

# Inject the live URL from settings rather than alembic.ini. Migrations need DDL
# (and, on PostgreSQL, table-OWNER rights to ENABLE/FORCE RLS), so they run as the
# admin/owner role via ALEMBIC_DATABASE_URL; the *runtime* app connects as the
# separate non-owner role in DATABASE_URL and is therefore bound by RLS. When
# ALEMBIC_DATABASE_URL is unset (dev/SQLite, single-role setups) it falls back to
# DATABASE_URL, so behaviour is unchanged there.
_migration_url = os.getenv("ALEMBIC_DATABASE_URL") or get_settings().database_url
# set_main_option/get_section run through ConfigParser interpolation, which
# treats '%' specially - so a legitimate '%' in a DB password must be doubled to
# survive the round-trip.
config.set_main_option("sqlalchemy.url", _migration_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # batch mode lets SQLite alter tables via recreate
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
