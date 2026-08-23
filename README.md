# Plenilo.com

A job board for Pakistan. FastAPI + PostgreSQL on the back, React + Vite on the
front, served same-origin behind one reverse proxy.

| | |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, Redis 7 |
| Frontend | React 19, TypeScript 5.7, Vite 8, React Router 8, React Query 5, Zustand 5 |
| Size | ~18,800 lines Python, ~11,700 lines TypeScript |
| API | 60 endpoints + `robots.txt` / `sitemap.xml` |
| Tests | 246 backend tests, 57 visual snapshots |

---

## Quick start

Two terminals. Postgres and Redis run in Docker on non-default ports so they
cannot collide with anything already installed on the host.

**Backend**

```bash
cd backend
docker compose up -d               # postgres :5433, redis :6380
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
pnpm install
pnpm dev                           # vite on :8443
```

**Admin Account**
// some thin i need to change to make new live 
email:asim@plenilo.com
password:blrdqYGl0$LbNW!poudC

Open <http://localhost:8443>. Vite proxies `/api`, `/sitemap.xml` and
`/robots.txt` to `127.0.0.1:8000`, so the browser only ever talks to one origin
— which is what production does too. That is not a convenience: the refresh
cookie is `SameSite=Strict` and a cross-origin dev setup could not authenticate
at all.

**First admin**

```bash
cd backend
.venv/bin/python -m app.cli bootstrap-admin \
  --email you@plenilo.com --name "Your Name" --generate-password
```

Sign in at <http://localhost:8443/admin/login>.

---

## Architecture

```
router  →  service  →  repository  →  database
```

Routers do HTTP only: parse, authorise, serialise. Business rules live in
services. SQL lives in repositories. No layer reaches past the next one, and no
router contains a business rule.

Every mutation writes an audit entry. Public actions (submitting a report,
recording an analytics event) do not — audit is for accountable actors.

### Backend layout

```
backend/app/
  api/v1/routers/   HTTP surface, one module per resource group
  services/         business rules (16 modules)
  repositories/     SQL (13 modules)
  models/           SQLAlchemy tables
  schemas/          Pydantic request/response contracts
  core/             config, enums, permissions, logging, rate limiting
  tasks/            APScheduler definitions and task bodies
  storage/          generated-asset backends (local filesystem today)
  cli.py            bootstrap-admin, seed-taxonomy, run-task
```

### Frontend layout

```
src/
  app/          router, query client
  pages/        public pages
  routes/       route-level components, admin console sections
  components/   shared UI
  lib/api/      typed API layer over Axios + response adapters
  hooks/queries/ React Query hooks (the only place data is fetched)
  stores/       Zustand: auth, saved jobs, preferences, toasts
  design-system/ tokens and variants
```

Public routes: `/`, `/jobs`, `/jobs/:slug`, `/saved-jobs`, `/categories`,
`/about`, `/contact`.
Admin console at `/admin/dashboard/*`: dashboard, jobs, add-job, reports,
analytics, categories, locations, sources, settings.

---

## Domain model

**Job lifecycle** — `draft → scheduled → published → expired → archived`.
Transitions are enforced in the service layer; the scheduler expires published
listings past their expiry date overnight.

**Concurrency** — admin writes use optimistic locking. `PATCH` requires an
`If-Match: <version>` header and returns `409` if another editor saved first.
Reports have no version column and use `SELECT … FOR UPDATE` instead.

**Search** — PostgreSQL full-text with a weighted `tsvector` and four tiers of
degradation, so a query that matches nothing exactly still returns something
useful rather than an empty page.

**Analytics** — eight event types (`job_view`, `apply_click`, `search`, `share`,
`report_created`, `source_click`, `job_saved`, `filter_used`) written to a
monthly range-partitioned table, rolled up daily. Rollups use
`INSERT … ON CONFLICT DO UPDATE` that *replaces* rather than increments, so
re-running a rollup is idempotent.

**RBAC** — 20 permissions across four roles: `super_admin` (20), `admin` (17),
`editor` (7), `analyst` (4). Changing an admin's role invalidates their cached
permission set in Redis immediately.

**Auth** — short-lived JWT access tokens plus opaque refresh tokens with
rotation. Replaying a rotated token outside a 10-second race window revokes the
whole token family. The frontend does single-flight refresh on `401`.

---

## Background jobs

APScheduler, in-process, no Celery. Every task takes a Postgres advisory lock
before doing work, so running several API instances does not multiply the work —
that is the property that makes in-process scheduling viable at all. Times are
in `Asia/Karachi`.

| Task | When | What |
|---|---|---|
| `ensure_partitions` | hourly | keep the partition window ahead of now |
| `rebuild_rollups` | every 15 min | recompute today's and yesterday's rollups |
| `expire_jobs` | 00:05 daily | expire listings past their expiry date |
| `purge_sessions` | 03:00 daily | delete expired refresh sessions |
| `prune_telemetry` | 04:00 monthly | drop partitions past retention |
| `alert_on_reports` | every 30 min | flag listings at the open-report threshold |
| `refresh_suggestions` | every 20 min | rebuild the autocomplete skill and popular-query vocabularies |

Run one by hand:

```bash
.venv/bin/python -m app.cli run-task --list
.venv/bin/python -m app.cli run-task ensure_partitions
```

---

## Operations

```bash
curl localhost:8000/health     # liveness
curl localhost:8000/ready      # postgres + redis + scheduler
curl localhost:8000/metrics    # prometheus
open http://localhost:8000/docs
```

`/metrics` requires `Authorization: Bearer <METRICS_TOKEN>` when that setting is
non-empty — the endpoint reveals traffic shape, route names and error rates.

Structured JSON logging is off locally (`JSON_LOGS`) because JSON in a terminal
is a wall a human has to pipe through `jq`. Rate limiting is Redis-backed and
fails open.

Outside `local` and `test`, startup refuses to proceed on a `SECRET_KEY` shorter
than 32 bytes or equal to a known default. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Features

### Reports

Readers report a listing as expired, suspicious, a broken link, a duplicate,
incorrect information, or other (comment required). Moderators work the queue
`open → under_review → resolved | dismissed`. Every moderator action is audited
with a verb that reflects the actual transition — reopening a dismissed report
is not the same event as picking up a fresh one.

### Social share assets

Two card designs rendered with Pillow: square (1080×1080 — WhatsApp,
Instagram, X) and landscape (1200×627 — LinkedIn, Facebook, `og:image`). They
are separate designs rather than one crop; the landscape card fits fewer skill
chips. Programmatic layout with a measure pass before the draw pass, bundled
Noto fonts, and drawn vector icons rather than emoji (Noto Sans has no emoji
coverage — they rendered as tofu boxes). Assets are keyed by a content hash, so a card regenerates only when
the listing text actually changed. Captions are generated per network (LinkedIn,
WhatsApp, Facebook, X).

`GET /api/v1/admin/jobs/{id}/share-assets` returns the URLs; the admin console
opens a share modal. The images are deliberately reachable at a public,
stable URL (`/api/v1/jobs/{slug}/social/{variant}.png`) so SEO work can point
`og:image` at the same file later — that integration is not built yet.

### Autocomplete search

`GET /api/v1/search/suggest?q=` returns grouped suggestions across job titles,
companies, skills, locations and categories. `GET /api/v1/admin/search/suggest`
adds sources and includes drafts and expired listings — a separate authorised
endpoint rather than a flag, because "may this caller see unpublished titles?"
does not belong in a query parameter.

Ranking runs in four tiers: exact prefix, then terms matching a popular search,
then full-text, then trigram fuzzy. Within a tier the tiebreak is job count.

Everything is one `UNION ALL` round trip — six sequential queries could not fit
the 100ms budget. Two vocabularies are materialised by the scheduler because
their sources cannot be read fast enough per keystroke: skills live in a JSONB
array with no usable index, and query popularity spans a partitioned table.

The fuzzy tier uses the `%` operator, never `similarity(col, q) > threshold`.
They return identical rows; only the first can use the trigram GIN index. At
50k vocabulary rows that is 12ms against 158ms, and `test_suggest.py` asserts
the query plan so the difference cannot regress silently.

The front end debounces at 300ms, idles below two characters, supports arrow-key
navigation with Enter and Escape, highlights the matched span client-side (the
server returns plain text so a per-keystroke payload is never trusted as HTML),
and closes on outside click. `tools/suggest-e2e.mjs` drives a real browser
through all of it.

### AI job description tools

Two admin-only endpoints backed by the Anthropic API:

- `POST /admin/ai/rewrite` — improves grammar and readability while preserving
  meaning, skills, salary and requirements
- `POST /admin/ai/generate` — drafts a description from the structured job
  fields

Output is shown side by side with word-level diff highlighting, and the editor
accepts or rejects each field individually. **Nothing generated is stored until
the admin submits the job form** — `ai_service.py` performs no database writes.

Set `ANTHROPIC_API_KEY` to enable. Without it both endpoints return `503` and
the console shows a persistent "not configured" note instead of a toast, since
retrying would fail identically.

---

## Development

### Backend

```bash
cd backend
make up                      # start postgres + redis
make migrate                 # alembic upgrade head
make check                   # fail if models and database have drifted
make lint                    # ruff
.venv/bin/python -m pytest -q   # 246 tests, ~4.5 min
```

Migrations are `backend/alembic/versions/0001` … `0007`. Alembic uses a naming
convention that prefixes constraints automatically — pass the **short** name in
a migration or it gets double-prefixed.

### Frontend

```bash
pnpm dev
pnpm build
pnpm exec tsc --noEmit
pnpm snapshot <outDir>                       # render 57 snapshots
pnpm snapshot:diff <baseline> <candidate>    # compare appearance, not bytes
node tools/diff-probe.mjs                    # exercise the AI review diff
node tools/verify-auth.mjs                   # auth round-trip against a live API
```

`snapshot:diff` compares the ordered sequence of style declarations and the
visible text, both parsed through the same CSS engine. Swapping a `<button>` for
an `<a>` with identical styling passes; changing a colour or a spacing value
fails.

> **Do not run `pnpm format`.** The pinned oxfmt corrupts TypeScript — it strips
> `;` from inline type literals and rewrites `(keyof T)[]` as `keyof T[]`, which
> breaks the build across the codebase.

---

## Configuration

`backend/.env`, seeded from `backend/.env.example`. Everything is typed in
`app/core/config.py` and missing required values raise at import time, so a
misconfigured deployment fails on startup rather than on the first request that
happens to need them.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `local` | `local` \| `test` \| `staging` \| `production` |
| `POSTGRES_*` | port `5433` | matches `docker-compose.yml` |
| `REDIS_URL` | `redis://localhost:6380/0` | 6380 avoids a host Redis on 6379 |
| `SECRET_KEY` | — | ≥32 bytes required outside local/test |
| `SITE_URL` | `http://localhost:8443` | absolute URLs in sitemap and structured data |
| `ANTHROPIC_API_KEY` | empty | unset ⇒ AI endpoints return `503` |
| `AI_MODEL` | `claude-opus-5` | pinned, not `latest` |
| `SCHEDULER_ENABLED` | `true` | disable on request-only instances |
| `CACHE_ENABLED` | `true` | "caching off" is a legitimate operational state |
| `RATE_LIMIT_ENABLED` | `true` | off in tests |
| `METRICS_TOKEN` | empty | when set, `/metrics` requires it |
| `JSON_LOGS` | `false` | on in staging and production |

---

## Not built yet

Honest list of what is missing, so nobody rediscovers it the hard way.

- **SEO** — `robots.txt` and `sitemap.xml` exist, but the site is still
  `noindex` (`.figma/make/site.json`) and there is no per-route meta or
  `JobPosting` JSON-LD. Un-blocking indexing before those exist would get ten
  identical pages indexed.
- **Analytics producers** — the ingest endpoint, tables, rollups and dashboards
  are all built and tested, but the frontend does not emit events yet, so
  dashboards read zero on a fresh database.
- **Public report UI** — `POST /reports` has no consumer; the moderation queue
  is complete on the admin side.
- **Site settings** — the admin Settings screen renders fields with no endpoint
  behind them. The save button is disabled and says so rather than reporting a
  success nothing stored.
- **Contact form delivery** — the form validates and confirms locally; nothing
  is sent or persisted yet.
- **Legal copy** — the Privacy Policy and Terms pages describe how the product
  actually behaves, but have not been reviewed by a lawyer and still carry
  `[bracketed]` placeholders for the operating entity.
- **`og:image` wiring** — share assets are generated and publicly addressable
  but not referenced from any page's meta tags.
- **Deployment** — no reverse proxy config, TLS, secret management or backup
  policy in this repository.
- **Dev database residue** — test accounts and listings from milestone test runs
  are still present locally.
- `backend/Makefile`'s `run` target carries a stale comment ("no routes until
  milestone 2").
