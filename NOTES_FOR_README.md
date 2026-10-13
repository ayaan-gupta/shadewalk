# Notes for the README

Facts only. Every number here was measured in the build session on 12 October 2026, with the command that produced it.

## Quickstart, ports, env

- One command from a clean clone: `make dev`. It creates `.venv` (needs `python3.12` on PATH, or `PYTHON=/path/to/python3.12 make dev`), installs `api/requirements.txt`, runs `npm ci` in `web/`, starts PostGIS with a plain `docker run` (container `shadewalk-db`), seeds it from the committed dataset, then serves the API and the web app.
- Tested from a fresh `git clone` into a temp directory: both servers answered after 33 s, `store` was `postgis`, a route came back through the web proxy, `make test` passed (41 passed, 1 skipped, plus 11 vitest), `make test-db` passed (42 passed).
- No Docker: `make dev-files`. Same app, the API reads `data/pilot` directly. `make dev` also falls back to this on its own when Docker is not running.
- `docker compose` is not installed on the build machine, so there is no compose file. The database is one `docker run`, published on 127.0.0.1 only.
- Ports: web 4107, API 8107, Postgres 5507 on the host. All three are env-overridable.
- Env vars (all optional, see `.env.example`): `WEB_PORT`, `API_PORT`, `POSTGRES_PORT`, `POSTGRES_PASSWORD`, `POSTGIS_IMAGE` (default `imresamu/postgis:17-3.5`, because `postgis/postgis` has no arm64 build), `DATABASE_URL`, `SHADEWALK_NO_DB`, `WEATHER_PROVIDER` (`offline` or `open-meteo`), `WEATHER_TIMEOUT_S`, `WALK_SPEED_MPS` (1.3), `SHADEWALK_DATA_DIR`, `CORS_ORIGINS`, `VITE_MAP_STYLE_URL` (default OpenFreeMap positron, or `offline`), `VITE_API_BASE`, `OVERPASS_URL` (pipeline only), `PYTHON`.
- Other commands: `make test`, `make test-db`, `make acceptance`, `make data`, `make demo`.

## The pilot

- Downtown Dallas and the Arts District, bbox `-96.8060, 32.7765, -96.7935, 32.7905`, about 1.8 km2. Chosen over Uptown, Deep Ellum and central Fort Worth after pulling all four: it has the towers that make afternoon shade, sidewalks mapped as separate ways on both sides of most streets, 104 bus stops and 16 rail stops.
- Graph: 2,388 nodes, 3,272 segments, 100.7 km (60.7 km sidewalk, 21.8 km service lanes and parking aisles, 9.6 km paths, 5.3 km crossings). 121 indoor, tunnel or private edges and 137 disconnected nodes were dropped. 3,023 segments carry a street label, borrowed from the nearest named road within 30 m when the sidewalk has no name.
- Buildings: 883 prisms from 662 OSM outlines and 217 building parts, including a 400 m buffer so neighbours cast shadows in. Height source by footprint area: OSM `height` 33.6%, `building:levels` x 3 m 25.1%, default 10 m 40.8%.
- Canopy: 1,989 polygons, 6.3% of the 1 m grid, median crown height 6.0 m.
- Committed dataset: `data/pilot`, 1.1 MB in 8 files. Raw pulls (54MB on this machine) stay in git-ignored `data/raw`.

## What each milestone delivered

- **M1:** osmnx walk graph for the pilot, a custom A* (checked against Dijkstra on 40 pairs), `POST /api/route`, MapLibre map UI with tap-to-place and a places menu.
- **M2:** pvlib sun table (every 15 min, 15th of each month, local clock time), building prisms from OSM, a raster shadow caster, and the shade table: 12 months x 24 hours x 3,272 segments, sampled every metre (102,343 samples). 142 daylight slots, two surfaces each, built in 24 s.
- **M3:** NAIP canopy segmentation with lidar heights, canopy added to the shade table as a second layer, the PRD cost in A*, the preference slider with the 1.5x rule, heat factor from temperature, Open-Meteo provider plus offline climatology.
- **M4:** time slider with a shadow overlay drawn from the model, planner view (blocks and transit stops ranked by sun and foot-traffic indicators, in PostGIS SQL with an in-memory twin), the independent 20 segment check, the field protocol, the acceptance script.

## Acceptance tests

Measured by `make acceptance` (writes `docs/acceptance.json`). 200 origin-destination pairs, seed 715, node pairs 300 m to 1.5 km apart in a straight line, July 15 at 3 PM, heat factor 0.96 from the 34.4 C climatology, default slider (w = 2).

| PRD acceptance test | Result | Measured | Where |
|---|---|---|---|
| Shadiest route has at least 25% more shaded length than the shortest, for at least 50% of pairs, 3 PM July | Met | With canopy: 174 of 200 pairs, 87.0%. Buildings only: 167 of 200, 83.5%. Median gain 23.9 and 24.3 points of shade. Routes identical for 10 and 20 pairs. | `validation/acceptance.py`, `test_acceptance_1_...` (120 pairs in the test) |
| Shadiest never more than 1.5x the shortest distance unless the slider is raised | Met | Max detour ratio at default slider: 1.259 with canopy, 1.290 without. Stress run (heat factor 1.5, months 1, 4, 7, 10 at 8, 11, 14, 17 h, 40 pairs each): max 1.496, so the cap binds and holds. Slider at maximum (cap 3.0): max 1.742. | `test_detour_never_exceeds_the_cap_...`, `test_raising_the_slider_...` |
| Hand-checked shade fractions at 20 segments agree within 15 points | Met as an independent computational check only. Not a field measurement. | 20 of 20 within 15 points. Max difference 2.7 points, mean 0.81, July 3 PM. Also 2.9 max in January 9 AM and 3.0 max in April 5 PM. | `validation/independent.py`, `test_acceptance_3_...` |
| Route response under 1 second | Met | In-process ASGI, 200 requests: p50 2.35 ms, p95 3.76 ms, max 22.8 ms. Live HTTP against uvicorn with the PostGIS store, 200 requests: p50 2.4 ms, p95 4.7 ms, max 10.2 ms. | `test_acceptance_4_...`, ad hoc httpx loop |

- "25% more shaded length" is read as `shaded_m(shadiest) >= 1.25 * shaded_m(shortest)` and strictly more. A shortest route with zero shade is beaten by any shade at all.
- How the third test was done: `independent.py` recomputes shade for 20 seeded segments (7 sunny, 7 mixed, 6 shady) by casting one ray per 0.25 m sample against the exact vector footprints and ray-marching the canopy raster, with its own NOAA sun equations and its own projection. A test parses its imports to prove it shares no code with the production shadow code. It shares the input data, so a wrong OSM height fools both.
- `docs/field-validation.md` is the protocol a person would follow on site for the same 20 segments, with coordinates, and `api/validation/field_template.csv` is the sheet. `python -m validation.field_protocol sheet.csv` scores a filled sheet.

## Test counts

- pytest: 42 tests. M1 7, M2 13, M3 11, M4 11. One (PostGIS parity) is skipped unless `DATABASE_URL` is set. `41 passed, 1 skipped` without a database, `42 passed` with it.
- vitest: 11 tests in 3 files (formatting and the detour rule, the art loader, the share card).
- `ruff check` clean, `mypy --strict` clean on `api/shadewalk` (19 files), `tsc --noEmit` clean with `strict` and `noUncheckedIndexedAccess`.

## Technical problems worth telling

- **Overpass refused every connection while curl worked.** osmnx resolves `overpass-api.de` once with `gethostbyname` and pins all later requests to that one address. The name is a round robin over two machines and the first record (65.109.112.52) was refusing connections. curl silently fell through to the second. My first fix was longer retries, which burned 25 minutes on nothing. The real fix probes the address osmnx will pin before using it and falls through to the machines' own hostnames. Then Overpass stopped answering from this machine altogether (other builds share the IP), so buildings, places, trees and road names came from the OSM API's `map` call in four tiles, which osmnx can filter by tag the same way. The walk graph had already come through Overpass. Both paths are in `pipeline/fetch_osm.py`.
- **Shadow casting without marching rays.** Marching every cell toward the sun costs cells times shadow length: about 2,000 steps over 4.6 million cells for a 200 m tower at a 5 degree sun. Instead the height raster is resampled into a frame whose columns point at the sun, and then "is anything sunward tall enough" is `max over j > i of (H[j] - j*k) > -i*k`, a suffix maximum that numpy does for every row at once. One cast takes about 0.2 s whatever the shadow length, and the whole table took 24 s.
- **Every shadow was half a metre short.** First check against a closed form: a 20 x 10 x 10 m box, sun due south at 45 degrees, should shade 200 m2 of ground. The raster said 180. Distances were measured between cell centres, but a column fills its cell, so its wall is half a cell closer. Subtracting half a step fixed it: 208 at 1 m cells, 200.0 at 0.5 m.
- **Texture did not separate trees from lawn.** The plan was NDVI plus local texture. On this image the 5x5 standard deviation of NIR has a median of 18.5 over tall vegetation and 22.1 over low vegetation, the wrong way round, because building edges and tower shadows dominate texture downtown. The height cue works: vegetation (NDVI above 0.10) is kept where the 2018 3DEP lidar surface stands at least 2.5 m above ground within two cells. Planetary Computer has no height-above-ground or terrain product for Dallas and the classification raster only has classes 1, 2 and 17, so ground is interpolated from the ground-classified cells.
- **The first NAIP read covered 10.9% of the grid.** Two quarter quads share the newest date and I took the one the catalogue listed first, the wrong one. Now tiles are ranked by overlap and mosaicked.
- **The 1.5x rule is a constraint, not a cost.** With cost `length * (1 + w * (1 - shade) * heat)` a route can only be guaranteed within 1.5x when `w * heat <= 0.5`, which is too weak to change many routes. So the router bisects w down to the largest value whose route fits the cap (ten steps, p95 still under 5 ms). The stress run shows it binding at 1.496.
- **Smaller ones:** a `typeof import.meta.glob` guard emptied the art table, because Vite rewrites the call at build time and the function does not exist at run time. On a viewport resize the planner's fly-to effect re-fired and dragged the map away from the route.

## Surprises and things I got wrong first

- I expected the 25% test to be close. It passed at 87%, because downtown Dallas has sidewalks mapped as separate ways on both sides of the street, so the router can often just cross to the shady side for a median detour of 5%.
- Canopy adds only 3.5 points to that test (83.5% to 87.0%) even though it raises network shade at 3 PM in July from 18.2% to 25.7%. Tower shade already gives the router most of its choices downtown.
- `3 m per level` under-reads this area. For footprints with only a level count, the OSM-derived median is 15.0 m and the lidar median is 22.3 m. For untagged footprints the lidar median is 10.4 m, which is where the 10 m default comes from (it started as a guess of 9).
- Of 572 trees mapped by hand in OSM, 305 (53%) fall within 3 m of segmented canopy. The misses are mostly young street trees: too small in 2018 lidar or planted after it.
- In the demo, raising the slider to its maximum did not change the Klyde Warren to Main Street Garden route. The default already finds the shadiest sensible way for that pair.
- Two of my own tests were wrong, not the code: an arithmetic slip in the cost test, and assuming no bus stop sits exactly on a sidewalk (21 stop and segment pairs are at distance zero, because the stop is a node of the way).

## Limitations

- Not validated in the field. The 20 segment check is a second computation of the same model.
- One pilot area. Nothing outside the bbox routes.
- 40.8% of building footprint area has no height in OSM and gets 10 m. Shade near those buildings is a guess.
- Lidar is from 2018 and the image from July 2022, so trees planted since 2018 are mostly missing and anything built since is absent or wrong.
- Canopy is a solid block from the ground to its top. Real crowns let low sun under them.
- Flat ground. Elevated freeway decks are not modelled, so sidewalks under I-345 read as sunny. Awnings, arcades not tagged `covered`, bus shelters and street furniture are invisible.
- Shadows from towers more than 400 m outside the pilot are missed, which matters only at low sun. Below 2 degrees of elevation everything is called shade.
- Hourly table on one day per month. A 3:20 PM request blends two rows, and a walk is treated as instantaneous.
- Start and end snap to the nearest graph node, not the nearest point on a path.
- Parking aisles and service lanes are walkable in the graph (21.8 km of it). Some are not pleasant or public.
- The heat factor is a straight line on air temperature: 0 at 20 C, 1 at 35 C, 1.5 at 42.5 C. No humidity, no heat index.
- "Cooling" markers are OSM libraries and museums, not an official cooling centre list. No opening hours.
- The planner's demand is a count of nearby stops and schools, not pedestrian volume.
- No geocoder. Places come from named OSM features in the pilot or a tap on the map.
- The base map needs the network (OpenFreeMap). Without it the app falls back to its own buildings, walkways and shadows on plain paper.

## Next three ideas

- Use the lidar surface as a building height source where OSM has none, and re-run the independent check and the acceptance tests to see how far the routes move.
- Do the field protocol: 20 segments, four people, one July afternoon. Then fit the model's worst assumption to what they find.
- Shade at the bus stop as a first-class result: rank stops by minutes of sun during service hours and join DART ridership, so the planner view points at shelters, not only trees.

## Real and stand-in

- **Real:** OSM walk graph, buildings, stops and schools. NAIP imagery (item `tx_m_3209610_se_14_060_20220704`) and 3DEP lidar (`TX_Pecos_Dallas_B3_2018`) through the Planetary Computer, no key. pvlib sun positions. ERA5 climatology through the Open-Meteo archive (87,672 hours, 2015 to 2024). PostGIS (seeded in 3.4 s, 942,336 shade rows). The route numbers in the demo.
- **Real but off by default:** the Open-Meteo forecast provider (`WEATHER_PROVIDER=open-meteo`). Tested against a recorded response in `api/tests/fixtures`, not exercised live in the app during this session.
- **Offline stand-ins:** the default weather is the committed climatology table. The file store replaces PostGIS in tests and in `make dev-files`. The map falls back to no base tiles.
- **Art:** all eight images are hand-written SVG in `assets/interim`, requested as generated art in `assets/prompts.md`, none delivered. No image generator was used. Nothing generates images at run time.
- **No LLM, SMS or speech model anywhere in this project.**
- **Not tested here:** `.github/workflows/ci.yml` has never run on GitHub. `make data` end to end in one go (the steps were run one at a time, and Overpass was down for the last pull).

## Files in docs/

- `demo.gif`: 98 frames, 2.7 MB. First-run screen, a route at 3 PM in July, the same walk at 9 AM, the slider raised, the share card, the shade map through a July day, the planner view.
- `screen-onboarding.png`: first-run screen with the interim landing illustration and six icons.
- `screen-route.png`: shortest (dashed) and shadiest (coloured by shade) routes with the result cards.
- `screen-shade.png`: shade map at 3 PM in July, every walkway coloured by shade fraction over the shadow layer.
- `screen-planner.png`: planner view, sunniest blocks near stops and schools, stops coloured by their own shade.
- `screen-share.png`: the share dialog. `share-card.png`: the 1200 x 630 PNG the browser exported.
- `screen-phone.png`: route view at 390 px wide.
- `acceptance.json`: full output of `make acceptance`, including the 20 segments.
- `field-validation.md`: the on-site protocol and segment list.
