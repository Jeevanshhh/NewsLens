# Real PostgreSQL RLS verification

`tests/test_postgres_rls_enforcement.py` exercises the database-level
Row-Level-Security boundary **against an actual PostgreSQL server** (the offline
`test_postgres_rls.py` only covers application-layer `WHERE user_id` scoping on
SQLite - RLS cannot exist there).

The module **self-skips** unless `NEWSELENS_PG_TEST_URL` points at a reachable
PostgreSQL instance whose role can `CREATE DATABASE` and `CREATE ROLE`. It then
creates a throwaway database + a non-owner `NOBYPASSRLS` runtime role, runs the
full Alembic chain (including the enforcement revision `d4e5f6a7b8c9`), seeds
two users, and asserts the allow/deny matrix. Everything is dropped afterwards.

## One-command setup (Docker, preferred)

```bash
docker run -d --name newslens-rls-test -e POSTGRES_PASSWORD=pw -p 55432:5432 postgres:16-alpine
# wait for it to accept connections, then:
cd backend
NEWSELENS_PG_TEST_URL="postgresql+psycopg://postgres:pw@127.0.0.1:55432/postgres" \
  ./.venv/bin/python -m pytest tests/test_postgres_rls_enforcement.py -v
```

## Against an existing local server

Set `NEWSELENS_PG_TEST_URL` to an admin connection string (URL-encoded password
if it contains special characters) and run the same `pytest` command. PowerShell:

```powershell
$env:NEWSELENS_PG_TEST_URL = "postgresql+psycopg://postgres:pw@127.0.0.1:5432/postgres"
.\.venv\Scripts\python.exe -m pytest tests/test_postgres_rls_enforcement.py -v
```

## Without putting the password in the shell (as verified on this machine)

`backend/run_pg_tests.py` is the credential-free runner used for the verified
run: it reads the admin password from the existing local
`%APPDATA%\postgresql\pgpass.conf` **into memory only**, exports it as
`PGPASSWORD` for the process, sets
`NEWSELENS_PG_TEST_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres`
(no inline password), and executes the 15-test module with JUnit output. The
password is never written to any file, URL, log, or command line.

```powershell
cd backend
.\.venv\Scripts\python.exe run_pg_tests.py
```

**Last verified:** 2026-09-25 against a local PostgreSQL **18.4** server -
15 passed / 0 failed / 0 skipped, throwaway database and roles dropped by the
fixture teardown.

## What it proves

| Scenario | Expectation |
|---|---|
| User A selects/updates/deletes **own** bookmark / saved search / history / report | allowed |
| User A selects / updates / deletes **User B's** row | denied (invisible, `rowcount == 0`) |
| User A inserts a row **pretending to belong to B** | denied (`WITH CHECK` -> RLS error) |
| No authenticated context | only the anonymous (`user_id IS NULL`) scope is visible |
| Transaction **rollback** | the insert is not persisted |
| **Pooled connection reuse** (`pool_size=1`) | A committed identity is gone for the next transaction |
| `set_config(..., is_local=TRUE)` | value auto-reverts at `COMMIT` |
| `search_results` junction | isolated through its owning `searches` row |

The policies it tests are built by `app.database.rls_sql` - the **same module**
the production migration imports - so the verified DDL is the shipped DDL.

> The runtime role's table privileges are granted by the migration only when the
> `RLS_APP_ROLE` role already exists; role **creation** (with a real password) is
> an operator step - see `backend/migrations/postgres/init/00_create_app_role.sh`
> and `docker-compose.yml`.
