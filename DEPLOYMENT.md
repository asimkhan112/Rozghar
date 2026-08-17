# Deploying for testing — Vercel + Railway + Neon

Three services: **Neon** holds the database, **Railway** runs the API, **Vercel**
serves the frontend and proxies `/api` through to Railway.

That proxy is the one design decision worth understanding before you start.

## Why Vercel proxies the API

The frontend calls `/api/v1/...` — a **relative** URL (`src/lib/http.ts`). It has
always talked to its own origin, and in local development Vite proxies those
paths to the backend.

`vercel.ts` keeps that true in production. The browser only ever sees the Vercel
origin; Vercel forwards `/api/*` to Railway server-side.

The alternative — pointing the browser straight at `*.railway.app` — **breaks
admin sign-in.** The refresh cookie is `SameSite=Strict`, so the browser would
refuse to send it to a different site. Making that work would mean weakening the
cookie to `SameSite=None` and adding CORS to the API: two security-relevant
changes to application code, in order to accommodate a hosting choice. Proxying
costs one config file and changes nothing.

---

## 1. Neon — database

1. Create a project, region close to your users (`ap-southeast-1` for Pakistan).
2. Copy the **pooled** connection string (the host contains `-pooler`).
3. Keep `?sslmode=require`.

The application handles the two things hosted Postgres needs, automatically:
TLS is requested through `connect_args` because asyncpg rejects libpq's
`sslmode`, and prepared statements are disabled when the host looks pooled —
without that, a transaction pooler produces intermittent
`prepared statement "__asyncpg_..." does not exist` errors under load.

## 2. Railway — API

Create a service from this repository with **root directory `backend`**.

Environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon pooled string, verbatim |
| `ENVIRONMENT` | `staging` |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SITE_URL` | your Vercel URL — **not** the Railway one |
| `JSON_LOGS` | `true` |
| `ANTHROPIC_API_KEY` | optional; AI endpoints return 503 without it |
| `REDIS_URL` | optional; add a Railway Redis and paste its internal URL |

`railway.toml` supplies the start command: `alembic upgrade head` then uvicorn on
`$PORT`. Migrations run on every boot — they are idempotent, and a failed
migration exits the container rather than serving a half-migrated schema.

`SECRET_KEY` shorter than 32 bytes, or equal to a known default, refuses to boot
outside `local`/`test`. That is deliberate: forgeable tokens are worse than a
failed deploy.

Then create the first admin from Railway's shell:

```bash
python -m app.cli bootstrap-admin --email you@rozgar.pk --name "Your Name" --generate-password
```

## 3. Vercel — frontend

Import the repository, root directory **`/`** (the repo root, not `backend`).

One environment variable:

| Variable | Value |
|---|---|
| `API_ORIGIN` | the Railway public URL, e.g. `https://rozgar-api.up.railway.app`, no trailing slash |

`vercel.ts` reads it at build time. If it is missing the build fails on purpose:
without the rewrites every API call would return `index.html` with a `200`,
which looks like a JSON parsing bug rather than a missing setting.

## 4. Check it

```bash
curl https://your-app.vercel.app/api/v1/jobs?per_page=1   # through the proxy
curl https://rozgar-api.up.railway.app/ready              # postgres + redis + scheduler
```

Then sign in at `https://your-app.vercel.app/admin/login`. If sign-in works, the
proxy is doing its job — that is the thing most likely to be misconfigured.

---

## Known limits of a testing deployment

- **Generated share images do not survive a redeploy.** They are written to the
  container filesystem, which Railway discards. They regenerate on next request,
  so nothing breaks; it is wasted work, not data loss. A persistent volume or
  object storage fixes it when it matters.
- **The site is `noindex` and `robots.txt` is `Disallow: /`** in any environment
  that is not `production`. That is correct for a test deployment — it stops
  Google indexing a staging copy — and it means SEO cannot be evaluated here.
  The build deletes the static `dist/robots.txt` on purpose: Vercel gives
  "precedence to the filesystem prior to rewrites being applied", so leaving it
  would pin the deployment to a build artefact instead of letting the API
  decide per environment.
- **Without Redis**, read caching is off and rate limiting fails open. Verified
  working: `/ready` reports Redis `degraded` while the service stays `ready`.
- **The scheduler runs in the API process.** On more than one Railway replica,
  Postgres advisory locks stop the work being duplicated. Set
  `SCHEDULER_ENABLED=false` on any replica that should only serve requests.

## Does this lock the project in?

No. Everything added for hosting is additive and portable:

| Added | What it is | If you leave the platform |
|---|---|---|
| `vercel.ts` | build config + proxy rules | delete it; any reverse proxy does the same job |
| `backend/railway.toml`, `Procfile` | a start command | delete; the command is plain uvicorn |
| `DATABASE_URL` support | one connection string instead of five parts | keep it — every host supplies one |
| TLS / pooler `connect_args` | correctness against hosted Postgres | keep it — inert locally |

No application code branches on the platform. `src/` and `backend/app/` contain
no reference to Vercel, Railway or Neon; the only new runtime behaviour is that
a connection string can arrive whole instead of in pieces, and it is inert
locally (`connect_args` is `{}` with no `DATABASE_URL` set).

Moving to a VPS later means: point a reverse proxy at the two processes, set the
same environment variables, delete two config files. Nothing to rewrite.
