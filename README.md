# NewsLens — News Intelligence & Research Platform

NewsLens is a full-stack news aggregation, search and analytics application. It
collects headlines from public news providers, classifies them into topics, and
gives each logged-in user a private, searchable library with reading, bookmark,
saved-search and analytics features (including a world/location map).

> **Status.** This project has been through a structured productionization
> effort. PostgreSQL Row-Level Security (Phase 11), the ML topic classifier
> evaluation (Phase 12) and repository/secrets hygiene (Phase 13) have each been
> **verified against a real runtime**. Docker, staging hosting, browser QA and
> the remaining release phases are **not yet verified** and are documented
> honestly below. No claim in this file should be read as a legal-compliance or
> production-launch assertion unless the corresponding verification is listed as
> done.

---

## 1. What NewsLens is

A research-oriented news browser. Public news sources are scraped/collected,
enriched with topic + (optional) location metadata, and stored centrally. Users
register, then run searches and get **per-user** results, bookmarks, saved
searches, exportable reports and analytics. The article reader is
**copyright-safe**: NewsLens shows a short snippet, attribution and a link to the
original publisher — it never presents itself as the publisher.

## 2. Core features

- Search across collected articles with filters (source, topic, location, date) and sorting.
- Pagination, recent searches, and saved searches.
- Article reader with metadata, key information, related coverage and "Open original source".
- Personal library: bookmarks and saved searches (isolated per user).
- Analytics: totals, articles over time, and source / topic / location distributions plus a world map.
- Account lifecycle: register, login, JWT sessions, password reset, password change, settings.
- Light / Dark / System themes and responsive (mobile) layouts.
- Legal / informational pages: About, Privacy, Terms, Security, Copyright, Contact.

## 3. Architecture

```
Browser (React + Vite + TypeScript)
        │  HTTPS / JSON  (/api)
        ▼
FastAPI backend (JWT auth, SQLAlchemy, Alembic)
        │
        ▼
PostgreSQL (production; Row-Level Security)   |   SQLite (local dev only)
```

In the containerized stack an nginx front-end serves the built React app and
reverse-proxies `/api` to FastAPI (see `docker-compose.yml`). The classification
pipeline is layered: **rules first, then an ML fallback** (see §9).

## 4. Frontend

- Location: [`frontend/`](frontend/) — React 18 + Vite + TypeScript, `react-router-dom`.
- Key screens ([`frontend/src/pages/`](frontend/src/pages/)): `Home`, `ResultsPage`,
  `ArticleReader`, `AnalyticsPage`, `BookmarksPage`, `SavedSearchesPage`, `Profile`,
  `SettingsPage`, `Login`, `Register`, `ResetPassword`, `LegalPage`.
- Notable components ([`frontend/src/components/`](frontend/src/components/)):
  `LocationMap` (analytics world map), `Sidebar`, `Layout`, `ProtectedRoute`,
  `ExportMenu`, `ArticleCard`, theme/auth contexts under `src/theme` and `src/auth`.
- The base API URL is configurable via `VITE_API_BASE_URL`
  (see [`frontend/.env.example`](frontend/.env.example)); in dev the Vite proxy
  forwards `/api` to the backend.

## 5. Backend

- Location: [`backend/app/`](backend/app/) — FastAPI application.
- Entrypoint [`backend/app/main.py`](backend/app/main.py) wires logging, CORS, a
  versioned API router under `/api`, and a health endpoint.
- Routes under [`backend/app/api/routes/`](backend/app/api/routes/) (auth, search,
  articles, library, analytics, health, …).
- Collection & classification services under
  [`backend/app/services/processing/`](backend/app/services/processing/)
  (`pipeline.py`, `classifier.py`, `news_topics.py`, `news_topics_eval.py`,
  `news_topics_data.py`).
- Configuration is validated through
  [`backend/app/core/config.py`](backend/app/core/config.py) (pydantic-settings).

## 6. Database

- SQLAlchemy models; **Alembic** migrations under [`backend/migrations/`](backend/migrations/).
- **Production:** PostgreSQL. **Local dev:** SQLite is supported for convenience,
  but RLS (see §8) is a PostgreSQL-only feature and is verified against real
  PostgreSQL, never SQLite.
- Central/shared tables: `articles`, `users`.
- Per-user (RLS-protected) tables: `bookmarks`, `searches`, `search_results`, `reports`.
- Application code additionally keeps explicit `user_id` filtering — RLS is
  database-level defense-in-depth, not a replacement for app scoping.

## 7. Authentication

- JWT bearer tokens; passwords are hashed (never stored in plaintext).
- Token lifetime configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Sliding-window **login rate limiting** (`LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_SECONDS`)
  and a request **body-size cap** (`MAX_BODY_BYTES`) as defense-in-depth.
- Password-reset flow with expiring links (`PASSWORD_RESET_EXPIRE_MINUTES`). When
  SMTP is not configured (dev), reset emails are captured in an in-memory outbox
  rather than being silently faked as sent.
- The `sub` claim is the trusted source of the current user identity and feeds the
  RLS mechanism (§8).

## 8. RLS (Row-Level Security) architecture — verified

Enforced at the database layer on PostgreSQL (Phase 11, **FIXED AND VERIFIED**
against real PostgreSQL 18.4, 15/15 dedicated enforcement tests):

- The runtime application connects as a **non-owner** role:
  `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`, `NOBYPASSRLS`.
- `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY` on protected
  tables (FORCE also binds the table owner).
- Explicit per-command `SELECT / INSERT / UPDATE / DELETE` policies scoped to the
  current user.
- Per-request identity: the session sets a **transaction-local** GUC via
  `set_config('app.current_user_id', <jwt sub>, TRUE)` at each transaction begin
  (see [`backend/app/database/rls.py`](backend/app/database/rls.py)), so pooled
  connections cannot leak identity between requests.
- Migrations run as a **separate owner/admin role** (`ALEMBIC_DATABASE_URL`)
  because they need DDL rights that the runtime role intentionally lacks.
- Reproducible runner: `backend/run_pg_tests.py` (reads the local pgpass credential
  into memory only; never writes/prints it). See
  [`backend/tests/README_postgres_rls.md`](backend/tests/README_postgres_rls.md).

## 9. ML / topic classification — measured honestly

Pipeline (architecture preserved):

```
Rules (domain keyword classifier)
   └─ confidently classified → rule result
      otherwise ↓
   TF-IDF → ComplementNB → confidence threshold (0.30) → known topic / Other
```

- Rule-based/domain logic always has priority; the ML stage is a **fallback** used
  only when a headline is otherwise "Other" and `ENABLE_TOPIC_MODEL` is on.
- Evaluated on a 396-example, 11-class balanced corpus with a stratified,
  untouched holdout (seed 42). **Measured** holdout accuracy ≈ **0.586**; unseen
  real-world set ≈ **0.690**; low-confidence inputs **abstain to "Other"** rather
  than guess. These are *topic-signal* numbers on a small corpus, **not** a
  high-accuracy production classifier, and were **not** tuned toward a target.
- Full evidence: [`docs/ML_EVALUATION.md`](docs/ML_EVALUATION.md) and raw output
  `backend/ml_eval_evidence.txt`. Reproduce with `backend/run_ml_eval.py`.

## 10. Environment variables

Copy the templates and fill in real values — never commit the resulting `.env`.

- Root/backend template: [`.env.example`](.env.example) (API keys, `SECRET_KEY`,
  `DATABASE_URL`, `ALEMBIC_DATABASE_URL`, `RLS_APP_ROLE`, CORS, SMTP, limits, …).
- Frontend template: [`frontend/.env.example`](frontend/.env.example) (`VITE_API_BASE_URL`).
- `.env` / `.env.*` are git-ignored; only `.env.example` is tracked.
- All secrets live in environment variables / the git-ignored `.env` (or the
  hosting platform's secret store in production). Nothing sensitive is hard-coded;
  defaults in `config.py` are non-functional sentinels.

## 11. Local development

Backend (from `backend/`, using its virtualenv):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend (from `frontend/`):

```powershell
npm install
npm run dev        # Vite dev server, proxies /api to :8000
```

Dev defaults to SQLite unless a `DATABASE_URL` is provided.

## 12. Database migrations

Alembic, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade base
```

For production PostgreSQL, set `ALEMBIC_DATABASE_URL` to the **owner** role (DDL +
table ownership) while the app runs as the non-owner `RLS_APP_ROLE`. The RLS
enforcement migration grants the runtime role its privileges and turns on
ENABLE/FORCE RLS with per-command policies.

## 13. Testing

- Full backend suite (SQLite, offline-deterministic):

  ```powershell
  cd backend
  .\.venv\Scripts\python.exe -m pytest
  ```

  Last full run: **151 collected — 136 passed, 15 skipped, 0 failed, 0 errors**.
  The 15 skips are the PostgreSQL RLS module, which self-skips without a live
  server and is run separately (§8).
- Real PostgreSQL RLS suite: `python run_pg_tests.py` (15/15 on PostgreSQL 18.4).
- ML tests + evaluation: `pytest tests/test_news_topics.py tests/test_news_topics_eval.py`; `python run_ml_eval.py`.
- Frontend typecheck & build: `npm run build` (`tsc --noEmit && vite build`).

## 14. Docker

- Images/config exist: [`backend/Dockerfile`](backend/Dockerfile),
  [`frontend/Dockerfile`](frontend/Dockerfile),
  [`frontend/nginx.conf`](frontend/nginx.conf),
  [`docker-compose.yml`](docker-compose.yml) (services: `db`, `backend`, `frontend`),
  and the Postgres init script under
  [`backend/migrations/postgres/init/`](backend/migrations/postgres/init/) that
  provisions the non-owner runtime role.
- Intended run: `docker compose --env-file .env up --build`.
- **Verification status: NOT YET VERIFIED.** The containers have **not** been built
  and exercised on this machine as part of a completed phase (see Known
  limitations). Docker will only be marked verified after a real build/run/health/
  auth/RLS smoke test.

## 15. Deployment

Target production shape:

```
Browser → hosted React/Vite frontend → hosted FastAPI backend → managed PostgreSQL (+RLS), HTTPS
```

- The production runtime must **not** depend on `localhost`/`127.0.0.1` or a local
  PostgreSQL; it needs a hosted/managed PostgreSQL.
- Secrets (`DATABASE_URL`, `ALEMBIC_DATABASE_URL`, `SECRET_KEY`, provider keys) are
  supplied via the hosting platform's secret/environment mechanism, never Git.
- **Status: staging hosting is NOT yet performed.** No public URL exists yet; deployment
  is a later, still-pending phase.

## 16. Security

- Production **boot guard**: with `APP_ENV=production`, the app refuses to start
  while `SECRET_KEY` is still the insecure default or `CORS_ORIGINS` is wildcard /
  localhost-only (see `config.production_safety_errors()`).
- CORS restricted to explicit configured origins with credentials.
- Login rate limiting + request body-size cap.
- No sensitive values logged; secrets are env-only and git-ignored.
- Database-layer RLS + application-layer `user_id` scoping (defense-in-depth).
- A repository secret audit was run in Phase 13 with **no committed secrets found**
  (see Known limitations / the Phase 13 report).

## 17. Privacy / legal pages

Fronted by [`frontend/src/pages/LegalPage.tsx`](frontend/src/pages/LegalPage.tsx)
with content in `frontend/src/legal/content.ts` and nav slugs: `about`, `privacy`,
`terms`, `security`, `copyright`, `contact`. These pages describe what is
collected, account/data handling, deletion/export, third-party sources, and
original-publisher attribution. They are **informational disclosures only** and do
**not** constitute a formal GDPR/DPDP/legal-compliance certification.

## 18. Known limitations

- The ML classifier is a small-corpus topic signal (~0.59 holdout), not a
  high-accuracy model; it deliberately abstains on low confidence.
- Docker packaging is implemented but **not yet verified by an actual build/run**.
- Staging hosting, real browser QA, hosted security QA and screenshot evidence are
  **not yet completed**.
- Legal pages are best-effort disclosures, not a lawyer-reviewed compliance claim.

## 19. Production setup checklist (to complete before any public launch)

1. Provision managed PostgreSQL; create owner/migration role + non-owner runtime role (`NOBYPASSRLS`).
2. Set `DATABASE_URL`, `ALEMBIC_DATABASE_URL`, `RLS_APP_ROLE`, a strong `SECRET_KEY`,
   explicit `CORS_ORIGINS`, `PUBLIC_FRONTEND_URL`, provider keys and SMTP via the
   platform's secret store.
3. Run `alembic upgrade head`; **re-verify RLS** on the real server.
4. Deploy backend, then frontend (pointing at the production API URL); enable HTTPS.
5. Smoke-test health, register/login, search, reader, bookmarks, saved searches, analytics + map.
6. Re-run security QA through the hosted HTTP path (missing/invalid/expired JWT, cross-user isolation, headers, rate limits).

## 20. Rollback / recovery basics

- **Migrations:** Alembic is reversible in this project (`alembic downgrade <rev>`);
  capture the current revision before applying upgrades.
- **Database:** take a managed snapshot / `pg_dump` before any migration or deploy;
  restore-from-snapshot is the primary recovery path (backup automation is **not yet
  verified** and should be configured on the hosting provider).
- **Application deploys:** keep the previous image/release tag and redeploy it to
  roll back; because secrets are external, ensure prior revisions' env expectations
  still match.
- **Data safety:** per-user isolation is enforced by RLS + app scoping; do not weaken
  either to resolve an incident.

---

*See [`docs/ML_EVALUATION.md`](docs/ML_EVALUATION.md) and
[`backend/tests/README_postgres_rls.md`](backend/tests/README_postgres_rls.md) for
the underlying verification evidence.*
