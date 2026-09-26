#!/bin/sh
# ============================================================
# NewsLens backend container entrypoint.
#
# Gates API startup on a successful schema migration:
#   1. `alembic upgrade head` runs first (as the image's unprivileged user).
#   2. Only if it exits 0 is the server command (CMD / "$@") exec'd.
#   3. On migration failure `set -e` aborts here, the container exits
#      non-zero, and the platform marks the deploy failed - FastAPI never
#      serves traffic against an unmigrated schema.
#
# Why this lives in the image: Render's FREE plan does not support a
# preDeployCommand, so the migration step cannot run as a separate release
# phase there. The runtime DB role is unchanged: Alembic uses
# ALEMBIC_DATABASE_URL (owner/migration role, DDL rights) via
# migrations/env.py; the API keeps using DATABASE_URL (non-owner
# `newslens_app` role bound by RLS). No credential is ever echoed here.
#
# Dockerfile normalises CRLF and sets the exec bit at build time.
# ============================================================
set -e

echo "[entrypoint] running alembic upgrade head (migrations gate startup)" >&2
alembic upgrade head
echo "[entrypoint] migrations ok; starting server" >&2

exec "$@"
