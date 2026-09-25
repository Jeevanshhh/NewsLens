# Database migrations (SQLite → PostgreSQL / Supabase)

Schema is managed with **Alembic**. The chain is verified on every CI run.

| Revision | Purpose |
| --- | --- |
| `8e36985788d1` | Initial schema (articles, users, bookmarks, reports, searches, search_results). |
| `a1b2c3d4e5f6` | Account-lifecycle columns on `users`: `password_changed_at`, `reset_token_hash`, `reset_expires_at`. |
| `c3d4e5f6a7b8` | Row-Level Security policies on the user-owned tables (**PostgreSQL only**; no-op elsewhere). |

## Running

```bash
# from backend/
pip install -r requirements.txt          # add psycopg[binary] for Postgres
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/newslens
alembic upgrade head                     # apply all migrations
alembic downgrade -1                     # roll back one revision
alembic downgrade base                   # roll everything back
alembic revision --autogenerate -m "..."  # after editing models
```

`DATABASE_URL` is read from the environment / `.env` by `env.py` — credentials
are never stored in `alembic.ini`. With no `DATABASE_URL` set, the default is
local SQLite (`sqlite:///./newslens.db`), and the `create_all()` in the app
lifespan keeps development working without a migration step.

## Supabase

Use the **connection pooling** URI from the dashboard as `DATABASE_URL`
(a `postgresql://…:6543/…` string). Run `alembic upgrade head` against it once.
Supabase's own `supabase db push`/`db diff` is an alternative; this project keeps
Alembic as the single source of truth for its tables so app and DB schema stay in
lock-step.

## Row-Level Security (defence-in-depth)

The `c3d4e5f6a7b8` migration enables RLS on `bookmarks`, `searches` and
`reports` with a policy that keeps each row visible only to the user identified
by the transaction-local setting `app.current_user_id`; an unset value falls back
to the anonymous scope (`user_id IS NULL`) — mirroring the application's own
`WHERE user_id = …` filtering.

`app/database/rls.py` sets that variable per transaction from the authenticated
request's JWT subject (see `get_current_user_optional`). It is inert on SQLite.

**Important:** policies without `FORCE ROW LEVEL SECURITY` do **not** constrain a
role that owns the tables (Supabase's service/owner role, and the default backend
connection). This is intentional so the trusted backend keeps working. RLS here
therefore protects *non-owner client roles* (e.g. `anon`, `authenticated`) if the
database is reachable directly. To have RLS also bind the backend, connect as a
dedicated non-owner role and add `FORCE ROW LEVEL SECURITY` in a follow-up
migration.

The **primary, test-covered isolation** in this project is application-layer
per-user scoping (`WHERE user_id = :me` in the services) — RLS is an additional
layer, not a replacement. See `tests/test_postgres_rls.py`.
