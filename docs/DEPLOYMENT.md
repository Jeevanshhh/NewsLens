# NewsLens — Staging/Production Deployment Runbook (Phase 15)

This is the exact procedure to host NewsLens off the local machine. It was
prepared from this environment but **not executed here**: the sandbox has no
outbound network access to Vercel's API (verified: `vercel whoami` / `vercel login`
hang, no `~/.vercel/auth.json` is created), and no container runtime (Docker is
absent). Run these steps on a normal networked machine with your own accounts.
Nothing here is a claim that a deployment exists — it is a checklist to make one.

Target architecture (no `localhost`/`127.0.0.1` in the production runtime):

```
Browser → HTTPS → Vercel (React/Vite)  →  HTTPS → Hosted FastAPI  →  Managed PostgreSQL (+RLS)
```

Three independent tracks: **A** managed Postgres, **B** hosted backend, **C** Vercel
frontend. Do them in that order.

---

## A. Managed PostgreSQL (do first)

Any managed PG that lets you create roles works (Neon, Supabase, Render PG,
Railway PG, Fly PG). Two roles are required by the RLS design:

| Role | Purpose | Attributes |
|---|---|---|
| **owner / migration** | runs Alembic (DDL + owns tables) | `CREATEDB`, owns the schema |
| **runtime** (`newslens_app`) | the app connects as this | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS` — owns nothing |

A table **owner bypasses RLS**, so the app must connect as the *non-owner* role for
Row-Level Security to bind it (this is the Phase-11 verified design).

Create the database + runtime role (adjust names/passwords; run as superuser/owner):

```sql
CREATE ROLE newslens_app LOGIN PASSWORD '<strong-app-password>';
ALTER ROLE newslens_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE DATABASE newslens OWNER <owner_role>;
```

### A1. Verify RLS on the real server before any user traffic

Re-run the enforcement suite against this hosted DB (locally, or in CI):

```powershell
cd backend
$env:NEWSELENS_PG_TEST_URL="postgresql+psycopg://<admin>@<host>:5432/postgres"
.\.venv\Scripts\python.exe -m pytest tests\test_postgres_rls_enforcement.py -v -o addopts=
```

Expected: 15 passed. (On the developer machine this was already verified against
PostgreSQL 18.4 — see `backend/tests/README_postgres_rls.md`.)

---

## B. Hosted FastAPI backend (Railway / Render / Fly.io)

The backend is a stateful ASGI app with background collection + per-transaction
PostgreSQL session GUCs, so it needs an **always-on service**, not a
request-scoped function host. `backend/Dockerfile` is ready (reviewed in Phase 14).

**Required environment variables** (set in the platform's secret store — never in Git):

| Var | Value |
|---|---|
| `APP_ENV` | `production` |
| `SECRET_KEY` | a long random string (generate on-platform; app **refuses to boot** on the default) |
| `DATABASE_URL` | `postgresql+psycopg://newslens_app:<app-pw>@<pg-host>:5432/newslens` |
| `ALEMBIC_DATABASE_URL` | `postgresql+psycopg://<owner>:<owner-pw>@<pg-host>:5432/newslens` |
| `RLS_APP_ROLE` | `newslens_app` |
| `CORS_ORIGINS` | `https://<vercel-app>.vercel.app` (explicit; no `*`, no localhost) |
| `PUBLIC_FRONTEND_URL` | `https://<vercel-app>.vercel.app` |
| `ENABLE_TOPIC_MODEL` | `true` (optional ML fallback) |
| `GNEWS_API_KEY` / `NEWSDATA_API_KEY` | optional; Google News RSS needs none |
| `SMTP_*` | optional; if unset, reset emails go to the in-memory dev outbox, never faked as sent |

**Start / migration flow (Render FREE plan):**

Render's Free tier does **not** support a `preDeployCommand` / release phase, so
migrations run **inside the container at startup** instead:

```
1. container starts        -> backend/entrypoint.sh (Dockerfile ENTRYPOINT)
2. alembic upgrade head    -> owner connection via ALEMBIC_DATABASE_URL
3. ONLY if step 2 exits 0  -> exec uvicorn app.main:app --host 0.0.0.0 --port 8000
4. if step 2 fails         -> container exits non-zero; deploy fails visibly,
                              the API never serves traffic on an unmigrated schema
```

Startup is therefore gated on a successful migration on every boot; `alembic
upgrade head` is idempotent, so restarts are safe. The runtime app still
connects as the non-owner `newslens_app` role (RLS-bound) via `DATABASE_URL` —
the gating does not move the runtime onto owner credentials. On paid plans or
other platforms (Railway/Fly) you *may* additionally keep an external release
command (`alembic upgrade head`); it is no longer required and must not be
relied on for Render Free.

**Smoke test after deploy:**

```
GET https://<backend-host>/api/health        → {"status":"ok", ...}
GET https://<backend-host>/api/health/ready   → {"status":"ok","database":"up"}  (503 if DB down)
```

Keep `POSTGRES` port **private** to the platform's VPC/internal network — do not
expose 5432 publicly (the `docker-compose.yml` port map is for local only).

---

## C. Vercel frontend

`frontend/vercel.json` is already configured (Vite, build `npm run build`, output
`dist`, SPA rewrites that leave `/api/` alone).

1. Import the repo (root dir = `frontend`) or `vercel` from `frontend/`.
2. Build settings are auto-detected from `vercel.json`.
3. Environment variable:

   | Var | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://<backend-host>` (bare origin — the app appends `/api/...` itself) |

4. Deploy. Note the resulting `https://<vercel-app>.vercel.app` URL and put it into
   the backend's `CORS_ORIGINS` / `PUBLIC_FRONTEND_URL` (from §B), then redeploy the
   backend so CORS matches.

> If you prefer **same-origin** `/api` (no CORS coupling), front both with one
> reverse proxy (as `frontend/nginx.conf` does in the Docker stack) instead of
> setting `VITE_API_BASE_URL`.

---

## D. Post-deploy (enables Phases 16–18)

Once `https://<vercel-app>` loads and talks to the hosted API:

- **Phase 16** — real browser QA: home, register/login, search+filters, reader
  (copyright-safe + image fallback), bookmarks, saved searches, analytics + **world
  map**, profile, settings, light/dark/system, mobile viewports (375×812, 390×844,
  768×1024).
- **Phase 17** — capture the screenshot package to `docs/screenshots/…` from the
  live URL (no secrets/PII in images).
- **Phase 18** — hosted security QA over HTTP: missing/invalid/expired JWT;
  User A vs User B cross-user isolation (read/update/delete/insert); CORS;
  security headers/CSP; rate limiting; body limits; account deletion; data export.

**Do not mark any of these verified until the live URL is actually opened and used.**

## Rollback

- App: keep the previous image/release tag; redeploy it (external secrets mean env
  expectations must still match).
- DB: snapshot / `pg_dump` before each migration; restore-from-snapshot is the
  primary recovery. Alembic is reversible (`alembic downgrade <rev>`).
