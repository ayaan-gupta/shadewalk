#!/usr/bin/env bash
# One command from a clean clone: installs what is missing, starts PostGIS in Docker,
# loads the committed pilot dataset into it, and serves the API and the web app.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi

API_PORT=${API_PORT:-8107}
WEB_PORT=${WEB_PORT:-4107}
POSTGRES_PORT=${POSTGRES_PORT:-5507}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-shadewalk}
POSTGIS_IMAGE=${POSTGIS_IMAGE:-imresamu/postgis:17-3.5}
PYTHON=${PYTHON:-python3.12}

[ -x .venv/bin/python ] || "$PYTHON" -m venv .venv
.venv/bin/python -c "import fastapi, uvicorn, psycopg, numpy, pydantic_settings, httpx" 2>/dev/null || .venv/bin/pip install --quiet -r api/requirements.txt
[ -d web/node_modules ] || (cd web && npm ci --no-audit --no-fund)

if [ -z "${SHADEWALK_NO_DB:-}" ] && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' | grep -qx shadewalk-db; then
    docker start shadewalk-db >/dev/null 2>&1 || docker run -d --name shadewalk-db \
      -p "127.0.0.1:${POSTGRES_PORT}:5432" \
      -e POSTGRES_USER=shadewalk -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" -e POSTGRES_DB=shadewalk \
      "$POSTGIS_IMAGE" >/dev/null
  fi
  export DATABASE_URL=${DATABASE_URL:-postgresql://shadewalk:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/shadewalk}
  echo "PostGIS: container shadewalk-db on 127.0.0.1:${POSTGRES_PORT}"
else
  export DATABASE_URL=
  echo "PostGIS: skipped (no Docker, or SHADEWALK_NO_DB set). Serving the committed files directly."
fi

echo "API  http://127.0.0.1:${API_PORT}/api/health"
echo "Web  http://127.0.0.1:${WEB_PORT}"
trap 'kill 0' EXIT INT TERM
(cd api && exec ../.venv/bin/uvicorn shadewalk.main:app_factory --factory --host 127.0.0.1 --port "$API_PORT") &
(cd web && API_PORT="$API_PORT" WEB_PORT="$WEB_PORT" exec npm run dev) &
wait
