# ShadeWalk: working notes for Claude Code

Project 7 of 11 from "Project PRDs: 11 Builds for Claude Code". Slug `shadewalk`.

## Commands

- `make dev` starts PostGIS in Docker (127.0.0.1:5507), the API (8107) and the web app (4107). `make dev-files` does the same with no database.
- `make test` runs pytest, tsc and vitest. `make test-db` adds the PostGIS parity test.
- `make acceptance` measures the PRD acceptance tests and rewrites `docs/acceptance.json`.
- `make data` rebuilds `data/pilot` from OSM, NAIP, 3DEP lidar and Open-Meteo. Needs the network and `api/requirements-pipeline.txt`.
- `make demo` records `docs/demo.gif` and the screenshots against a running `make dev`.
- `cd api && ../.venv/bin/python -m validation.independent` prints the 20 segment check. `-m validation.field_protocol` rewrites the on-site protocol.
- Lint and types: `cd api && ../.venv/bin/ruff check . && ../.venv/bin/mypy`.

## Shared conventions

- **Repo:** one repo per project, named by its slug, MIT license, README.md with a demo GIF and a one-command quickstart.
- **Default stack:** TypeScript with Vite for web, Python (FastAPI) for services. This PRD adds MapLibre, PostGIS and osmnx.
- **Creative direction:** portfolio pieces, each with a distinct visual identity from its style bible. Here: flat vector, warm sunset palette against cool teal shade.
- **Image requests:** Claude Code does not generate images. Every image is requested from Ayaan in `/assets/prompts.md` with an asset ID, the exact prompt, size, format, save path under `/assets/generated`, and what it is for.
- **Quality bar:** typed code, at least 3 automated tests per milestone, no secrets in git, ARCHITECTURE.md of at most one page.
- **Definition of done:** runs from a clean clone with one command, passes all acceptance tests, deployed or recorded demo, README lists limitations and the next three ideas.

## How the image rule was applied here

Ayaan asked for this build to run with as few stops as possible, so the eight images were requested in `assets/prompts.md` without waiting. Hand-written SVGs in `assets/interim` stand in. `web/src/assets.ts` matches by path without extension, so a PNG in `assets/generated` replaces the SVG of the same name. Map tiles and the shadow layer are data, never generated art.

## Writing

No em dashes anywhere, in docs, comments or UI copy. README prose should sound like a person: varied sentences, no rule-of-three lists, no "it's not X, it's Y" constructions.

## Things that will bite

- Ports 3000, 8000 and 5432 are taken on this machine. Publish containers on 127.0.0.1 only. `docker compose` is not installed, so the database is a plain `docker run` in `scripts/dev.sh`.
- osmnx pins overpass-api.de to the first DNS record. When that machine is down every request is refused while curl works. `pipeline/fetch_osm.py` probes for a live endpoint and falls back to the OSM API map call.
- `import.meta.glob` is rewritten by Vite at build time and is undefined at run time. Never guard it with `typeof`.
- The shade table is indexed by segment id. Rebuilding the network without rebuilding the shade table gives wrong shade silently, so always run the pipeline steps in the Makefile's order.
- An SVG drawn into an `<img>` or a canvas cannot fetch other files. The share card inlines its template as a data URL first.
- `validation/independent.py` must stay free of imports from `shadewalk.shade`. That separation is the whole point of it.
- Headless Chromium needs `--use-angle=swiftshader --enable-unsafe-swiftshader` for MapLibre's WebGL.
