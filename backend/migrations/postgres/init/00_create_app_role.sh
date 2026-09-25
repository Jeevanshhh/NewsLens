#!/bin/bash
# ============================================================
# Provisions the separate, NON-owner runtime role for NewsLens.
#
# Runs once, at first data-directory initialisation, via the postgres
# image's /docker-entrypoint-initdb.d hook. The backend connects as this
# role so PostgreSQL Row-Level Security actually constrains it (a table
# owner bypasses RLS; this role does not own anything and cannot bypass).
#
# Privileges on the tables themselves are granted by the Alembic revision
# ..._enforce_rls_app_role.py (which runs as the owner) - NOT here - so the
# grant set stays a single source of truth with the policies.
#
# The password comes from APP_DB_PASSWORD (compose env / secret); it is never
# stored in source control.
# ============================================================
set -Eeuo pipefail

APP_ROLE="${RLS_APP_ROLE:-newslens_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	DO \$\$
	BEGIN
		IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_ROLE}') THEN
			CREATE ROLE "${APP_ROLE}" LOGIN PASSWORD '${APP_DB_PASSWORD}';
		ELSE
			ALTER ROLE "${APP_ROLE}" LOGIN PASSWORD '${APP_DB_PASSWORD}';
		END IF;
	END
	\$\$;
	-- Least privilege: no superuser / no role or db creation / cannot bypass RLS.
	ALTER ROLE "${APP_ROLE}" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
EOSQL

echo "Provisioned non-owner runtime role: ${APP_ROLE}"
