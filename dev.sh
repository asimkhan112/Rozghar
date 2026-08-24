#!/usr/bin/env bash
#
# Starts everything Plenilo needs for local development:
#
#   Postgres + Redis (Docker) -> migrations -> FastAPI on :8000 -> Vite on :8443
#
# Safe to run repeatedly. The first run also creates the Python virtualenv,
# installs both dependency sets and writes backend/.env; later runs skip
# whatever is already in place. Ctrl-C stops the API and the web server (the
# containers keep running — stop them with `cd backend && docker compose down`).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
PYTHON="${PYTHON:-python3.12}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${PORT:-8443}"

step() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
fail() { printf '\n\033[1;31mError:\033[0m %s\n' "$1" >&2; exit 1; }

# --- Docker ------------------------------------------------------------------
step "Checking Docker"
if ! docker info >/dev/null 2>&1; then
  echo "    daemon not responding — starting Docker Desktop"
  open -a Docker 2>/dev/null || fail "Docker Desktop is not installed."
  for _ in $(seq 1 60); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
  docker info >/dev/null 2>&1 || fail "Docker did not come up. Start it manually and retry."
fi
echo "    ready"

step "Starting Postgres and Redis"
(cd "$BACKEND" && docker compose up -d >/dev/null)
for _ in $(seq 1 60); do
  pg=$(docker inspect --format '{{.State.Health.Status}}' rozgar-postgres 2>/dev/null || echo none)
  rd=$(docker inspect --format '{{.State.Health.Status}}' rozgar-redis 2>/dev/null || echo none)
  [ "$pg" = healthy ] && [ "$rd" = healthy ] && break
  sleep 2
done
[ "${pg:-}" = healthy ] || fail "Postgres never became healthy. Check: cd backend && docker compose logs postgres"
echo "    postgres :5433 and redis :6380 healthy"

# --- Backend environment -----------------------------------------------------
# Ports here match docker-compose.yml, not the defaults in app/core/config.py.
if [ ! -f "$BACKEND/.env" ]; then
  step "Writing backend/.env"
  cat > "$BACKEND/.env" <<'ENVFILE'
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
USAJOBS_API_KEY=
USAJOBS_USER_AGENT=
ENVFILE
fi

# --- Python ------------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  step "Creating the Python environment (first run, takes a minute)"
  command -v "$PYTHON" >/dev/null 2>&1 \
    || fail "$PYTHON not found. The project needs Python >= 3.12; install it or set PYTHON=<path>."
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  (cd "$BACKEND" && "$VENV/bin/pip" install --quiet -e ".[dev]")
fi

# --- Node --------------------------------------------------------------------
if [ ! -d "$ROOT/node_modules" ]; then
  step "Installing frontend packages"
  command -v pnpm >/dev/null 2>&1 \
    || fail "pnpm not found. Install it with: npm install -g pnpm@10.34.3"
  (cd "$ROOT" && pnpm install)
fi

# --- Schema ------------------------------------------------------------------
step "Applying migrations"
(cd "$BACKEND" && "$VENV/bin/alembic" upgrade head 2>&1 | grep -E 'Running upgrade|ERROR' || true)
echo "    schema up to date"

# --- Servers -----------------------------------------------------------------
API_PID=""
WEB_PID=""
shutdown() {
  printf '\n\033[1;36m==>\033[0m Stopping\n'
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null || true
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap shutdown INT TERM EXIT

step "Starting the API on :$API_PORT"
(cd "$BACKEND" && exec "$VENV/bin/uvicorn" app.main:app --reload --port "$API_PORT") &
API_PID=$!

for _ in $(seq 1 30); do
  curl -sf -m 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf -m 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 \
  || fail "The API did not answer on :$API_PORT — see the log above."
echo "    healthy"

step "Starting the web app on :$WEB_PORT"
(cd "$ROOT" && exec pnpm dev) &
WEB_PID=$!

cat <<BANNER

  Web app     http://localhost:$WEB_PORT
  Admin       http://localhost:$WEB_PORT/admin/login
  API docs    http://localhost:$API_PORT/docs

  Ctrl-C stops both servers.

BANNER

# Exit as soon as either server dies, so a crash is not hidden by the other.
# Polled rather than `wait -n`, which macOS's bundled bash 3.2 does not have.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done
