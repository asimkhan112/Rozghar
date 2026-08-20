# Running Plenilo on this Mac

Everything in this file has been run on this machine, in this order, and works.
The short version:

```bash
cd /Users/applevalley/Desktop/projects/rozgar/Rozghar
./dev.sh
```

Then open **http://localhost:8443**.

---

## 1. What this project is

Plenilo is a Pakistani job board split into two halves that are served from a
**single origin** — that matters, because the refresh cookie is `SameSite=Strict`
and would not survive a cross-origin setup.

| Half | Stack | Runs on |
|---|---|---|
| Frontend | React 19, Vite 8, Tailwind v4, React Router 8, TanStack Query, Zustand, Axios | `:8443` |
| Backend | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, APScheduler | `:8000` |
| Database | PostgreSQL 16 (Docker) | `:5433` → container `5432` |
| Cache / rate limits | Redis 7 (Docker) | `:6380` → container `6379` |

In development Vite proxies `/api`, `/sitemap.xml` and `/robots.txt` to the API
(see [vite.config.ts](vite.config.ts)), so the browser only ever talks to
`:8443`. In production a reverse proxy does the same job.

**Layout**

- [src/](src/) — 74 TS/TSX files: [src/pages/](src/pages/) (public pages),
  [src/routes/admin/](src/routes/admin/) (admin panel), [src/lib/api/](src/lib/api/)
  (typed API client over [src/lib/http.ts](src/lib/http.ts)),
  [src/stores/](src/stores/) (auth, saved jobs, preferences, toasts),
  [src/hooks/queries/](src/hooks/queries/) (TanStack Query hooks).
- [backend/app/](backend/app/) — 98 Python files: 13 routers under
  [backend/app/api/v1/routers/](backend/app/api/v1/routers/), services,
  repositories, models, and an in-process scheduler
  ([backend/app/tasks/](backend/app/tasks/)) that takes Postgres advisory locks so
  multiple instances don't duplicate work.
- [backend/alembic/versions/](backend/alembic/versions/) — 7 migrations, from the
  initial schema through search, analytics and social assets.
- [tools/](tools/) — Node scripts for appearance snapshots and an auth-refresh check.

**Routes worth knowing:** `/` `/jobs` `/jobs/:slug` `/saved-jobs` `/categories`
`/about` `/contact`, `/admin/login`, and `/admin/dashboard/*` (jobs, add-job,
reports, analytics, categories, locations, sources, settings).

---

## 2. Prerequisites (state on this Mac)

| Tool | Needed | Here | Note |
|---|---|---|---|
| Docker Desktop | any recent | 29.4.3 ✅ | must be **running**, not just installed |
| Node | 22 pinned in `.mise.toml` | v26.0.0 ✅ | works; prints one harmless `module.register()` deprecation warning |
| pnpm | 10.34.3 | 10.34.3 ✅ | installed with `npm install -g pnpm@10.34.3` |
| Python | ≥ 3.12 | 3.12.13 ✅ | `python3` here is 3.14 — **use `python3.12`**, some deps have no 3.14 wheels |

If pnpm ever goes missing: `npm install -g pnpm@10.34.3` (Node 26 no longer
ships `corepack`, so that route is not available).

---

## 3. One command

[dev.sh](dev.sh) does the whole thing: starts Docker Desktop if needed, brings up
Postgres and Redis, creates the Python venv and installs deps on first run,
installs frontend packages, applies migrations, then runs the API and the web
server together. `Ctrl-C` stops both.

```bash
./dev.sh
```

| What | URL |
|---|---|
| Web app | http://localhost:8443 |
| Admin login | http://localhost:8443/admin/login |
| API docs (Swagger) | http://localhost:8000/docs |
| Health / readiness | http://localhost:8000/health · http://localhost:8000/ready |

**Local admin account** (already created on this machine, local database only):

```
admin@plenilo.com / LocalDev12345!
```

---

## 4. First-time setup, step by step

This has already been done here — it's written out so you can redo it after a
fresh clone, a wiped volume, or on another Mac.

### 4.1 Backend environment file

[backend/.env](backend/.env) is git-ignored and must exist. The important part is
that the ports match `docker-compose.yml` (5433 and 6380), **not** the defaults
in [backend/app/core/config.py](backend/app/core/config.py):

```bash
cat > backend/.env <<'EOF'
ENVIRONMENT=local
DEBUG=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=rozgar
POSTGRES_PASSWORD=rozgar
POSTGRES_DB=rozgar
REDIS_URL=redis://localhost:6380/0
SECRET_KEY=dev-only-change-me
SITE_URL=http://localhost:8443
ANTHROPIC_API_KEY=
EOF
```

`SECRET_KEY=dev-only-change-me` is accepted only when `ENVIRONMENT` is `local` or
`test`; anything else refuses to boot. `ANTHROPIC_API_KEY` empty means the admin
AI endpoints return 503 instead of erroring — everything else works.

### 4.2 Database and cache

```bash
cd backend
docker compose up -d
docker compose ps          # wait until both say (healthy)
```

Containers are named `rozgar-postgres` and `rozgar-redis`; data lives in the
`backend_plenilo-pgdata` volume and survives restarts.

### 4.3 Python environment

```bash
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e ".[dev]"
```

### 4.4 Schema and reference data

```bash
cd backend
./.venv/bin/alembic upgrade head          # 7 migrations
./.venv/bin/python -m app.cli seed-taxonomy   # 20 categories, 38 cities
```

### 4.5 First admin

There is no public registration — the first super admin comes from the CLI:

```bash
cd backend
./.venv/bin/python -m app.cli bootstrap-admin \
  --email admin@plenilo.com --name "Local Admin" --password 'LocalDev12345!'
```

Use `--generate-password` instead to have a strong one printed once (it is not
recoverable afterwards). Passwords must be at least 12 characters.

### 4.6 Frontend packages

```bash
pnpm install     # from the repo root
```

---

## 5. Running it by hand (two terminals)

Sometimes you want the two logs separate.

**Terminal 1 — API**

```bash
cd backend
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

(`make run` from `backend/` does the same thing.)

**Terminal 2 — web**

```bash
pnpm dev         # repo root; serves on 8443, proxies /api to 8000
```

Start the API first — the frontend's proxy target has to be there when the first
request goes out, though Vite itself will start regardless.

---

## 6. Everyday commands

### Backend (from `backend/`, or via `make`)

| Command | What it does |
|---|---|
| `make up` / `make down` | start / stop Postgres + Redis |
| `make migrate` | `alembic upgrade head` |
| `make downgrade` | roll back one revision |
| `make reset` | drop everything and rebuild the schema |
| `make check` | fail if models and database have drifted |
| `make verify` | round-trip migrations twice, then check drift |
| `make lint` / `make fmt` | ruff check / ruff format |
| `./.venv/bin/pytest` | the test suite (10 files) |
| `./.venv/bin/python -m app.cli run-task --list` | list scheduled tasks |
| `./.venv/bin/python -m app.cli run-task <name>` | run one immediately |

⚠️ **The tests use the same database as the app.** `backend/tests/conftest.py`
sets `ENVIRONMENT=test` but reuses the connection settings from `.env`, so a run
writes into your development data. Run `make reset && make migrate` afterwards if
you want a clean slate.

### Frontend (from the repo root)

| Command | What it does |
|---|---|
| `pnpm dev` | dev server on 8443 |
| `pnpm build` | production build to `dist/` |
| `pnpm preview` | serve the built output |
| `pnpm format` | oxfmt |
| `pnpm verify:auth` | headless check of the token-refresh logic |
| `pnpm snapshot <dir>` | render every page to static HTML for appearance diffs |
| `pnpm snapshot:diff` | compare two snapshot directories |

---

## 7. Troubleshooting

**`Cannot connect to the Docker daemon`** — Docker Desktop is installed but not
running. `open -a Docker`, wait ~20 seconds, retry. `dev.sh` does this for you.

**API exits with `[Errno 61] Connection refused` on startup** — Postgres isn't up
yet, or `POSTGRES_PORT` in `backend/.env` is 5432 instead of 5433.

**`ModuleNotFoundError` / build failures during `pip install`** — the venv was
built with Python 3.14. Delete it and rebuild with `python3.12`:
`rm -rf backend/.venv && python3.12 -m venv backend/.venv`.

**`pnpm: command not found`** — `npm install -g pnpm@10.34.3`.

**Port already taken** — the dev server uses `strictPort`, so it fails rather
than sliding to another port. Find the squatter with
`lsof -nP -iTCP:8443 -sTCP:LISTEN` (same for 8000, 5433, 6380). To move the web
port: `PORT=5173 pnpm dev`. To move the API: `--port 8001` on uvicorn plus
`API_ORIGIN=http://127.0.0.1:8001 pnpm dev`.

**`Refusing to start with an unsafe configuration`** — `ENVIRONMENT` is set to
something other than `local`/`test` while `SECRET_KEY` is still the default.

**`alembic check` reports drift** — models and migrations disagree; generate a
revision rather than editing the database by hand.

**No jobs on the home page** — expected on a fresh database. Categories and
locations come from `seed-taxonomy`; listings are created through
`/admin/dashboard/add-job`.

---

## 8. Current state on this machine

Already done, so `./dev.sh` is all that's left:

- `pnpm@10.34.3` installed globally; `node_modules/` populated
- `backend/.venv` built on Python 3.12.13 with all runtime + dev dependencies
- `backend/.env` written with the compose ports
- `rozgar-postgres` and `rozgar-redis` containers created and healthy
- All 7 migrations applied; 20 categories and 38 locations seeded
- Super admin `admin@plenilo.com` created and verified against
  `POST /api/v1/auth/login` through the Vite proxy
