PYTHON ?= python3.12
POSTGRES_PORT ?= 5507
VENV := .venv/bin

.PHONY: dev dev-files setup test test-db data acceptance demo db-stop

# The one command. PostGIS in Docker, API on 8107, web on 4107.
dev:
	./scripts/dev.sh

# Same app with no database: the API reads data/pilot directly.
dev-files:
	SHADEWALK_NO_DB=1 ./scripts/dev.sh

setup:
	[ -x $(VENV)/python ] || $(PYTHON) -m venv .venv
	$(VENV)/pip install --quiet -r api/requirements-dev.txt
	cd web && npm ci --no-audit --no-fund

# Everything that runs without a database or a network.
test: setup
	cd api && ../$(VENV)/python -m pytest tests -q
	cd web && npm run typecheck && npm test

# Adds the PostGIS parity test. Needs the shadewalk-db container (make dev starts it).
test-db: setup
	cd api && DATABASE_URL=postgresql://shadewalk:shadewalk@127.0.0.1:$(POSTGRES_PORT)/shadewalk ../$(VENV)/python -m pytest tests -q

# Rebuild data/pilot from public sources: OSM, NAIP, 3DEP lidar, Open-Meteo. Needs the network.
data:
	$(VENV)/pip install --quiet -r api/requirements-pipeline.txt
	cd api && for step in fetch_osm fetch_imagery build_network build_surface fetch_climate build_shade build_meta; do ../$(VENV)/python -m pipeline.$$step || exit 1; done

# Measure the PRD acceptance tests and write docs/acceptance.json.
acceptance:
	cd api && ../$(VENV)/python -m validation.acceptance

# Record docs/demo.gif and the screenshots against a running `make dev`.
demo:
	cd web && npm run demo

db-stop:
	docker stop shadewalk-db
