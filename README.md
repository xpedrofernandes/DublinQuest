# DublinQuest

### Explore Dublin Your Way

DublinQuest is a location-based exploration app for CMPU4058 — Advanced Web Mapping at TU Dublin. The idea is to help people discover Dublin through its street art, historic landmarks, public artworks and parks.

Instead of following a fixed tour, you choose where to start, what interests you, how far to explore and how many places to visit. DublinQuest uses those choices to put together an adventure on an interactive map.

## How it works

1. Choose an imported place suggestion, a popular starting-point shortcut, or click the map.
2. Select your interests, a search radius and the number of stops.
3. Explore the suggested stops using the map and an ordered list of places.
4. Follow your quest journey, mark stops as visited and keep track of your progress.

The map shows your start, search area and numbered destinations alongside an
ordered quest journey. Mark stops visited to update your progress; completion is
self-reported, not GPS-verified. See [Your first adventure](#your-first-adventure)
for the controls and mobile layout.

**A valid HeiGIT/openrouteservice key is required for pedestrian routes, walking
distances and estimated durations.** Without a successful routing response, the
app shows a straight-line sequence instead. See [Pedestrian routing](#pedestrian-routing)
for setup requirements and fallback limitations.

## Web mapping

The project uses real Dublin open data stored in PostgreSQL/PostGIS. Its spatial features include:

- Finding places within a chosen radius.
- Finding attractions inside a park's boundary.
- Finding parks and open spaces that overlap the search area.
- Storing places as points, park boundaries as polygons and adventure sequences as lines.
- Creating, viewing, editing and deleting spatial records through the authenticated DRF browsable API.

Adventures and visited stops are saved for the same browser, without requiring a visitor account.

## Technology stack

- **Backend:** Python, Django, GeoDjango and Django REST Framework
- **Database:** PostgreSQL with PostGIS
- **Map:** Leaflet.js and OpenStreetMap
- **Frontend:** HTML, CSS, JavaScript and Bootstrap 5
- **Local deployment:** Docker Compose and pgAdmin

## Scope

The project focuses on spatial searches, interactive mapping and a complete
exploration flow. The three spatial searches can be demonstrated independently of
quest generation. Live GPS tracking, turn-by-turn navigation and AI are outside
the project scope.

## Running locally

This guide starts from a fresh clone and an empty database volume. Docker Desktop
(or Docker Engine) must be running in Linux-container mode with Docker Compose v2.
No host Python, PostgreSQL or GIS installation is needed. Allow ports **8000** and
**5050**; internet access is needed for the initial build and OpenStreetMap tiles.
The four source datasets are already bundled in the repository.

I tested the fresh-clone setup on both macOS and Windows. On Windows, I used
Docker Desktop with its WSL2 backend. Run the guide from the project folder,
using the PowerShell alternatives where shown.

### 1. Clone the repository

```bash
git clone https://github.com/xpedrofernandes/DublinQuest.git
cd DublinQuest
```

If using the ZIP instead, extract it and open a terminal in the folder containing
`docker-compose.yml`, then continue below.

### 2. Configure the environment

```bash
cp .env.example .env
```

In Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` before starting containers:

- Replace every `change-me` value: `POSTGRES_PASSWORD`, `DATABASE_PASSWORD`,
  `DJANGO_SECRET_KEY` and `PGADMIN_DEFAULT_PASSWORD`. Use different random values;
  `openssl rand -hex 32` can generate each one.
- Keep `POSTGRES_USER` and `DATABASE_USER` different: the default names are
  `postgres` (administrator) and `dublinquest` (restricted application account).
- Keep `DJANGO_DEBUG=False` and the default localhost allowed hosts for this setup.
- `PGADMIN_DEFAULT_EMAIL` is the pgAdmin login name; set it to your preferred email.
- Configure **`ORS_API_KEY` for the intended pedestrian-routing experience** using
  the steps below. Leaving it blank permits core use with straight-line fallback,
  without pedestrian directions or walking estimates.
- Keep `DOCKER_SUBNET=172.28.40.0/24` unless it conflicts with another local network;
  choose a non-overlapping subnet before first startup if necessary.

Keep `.env` private. It is excluded from Git, the Docker build context and the
submission archive. Never replace `.env.example` with your real credentials.

If OpenSSL is unavailable on Windows, generate a random secret in PowerShell
(run again for each value):

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
$rng.Dispose()
```

To obtain and configure the routing key:

1. Register or sign in at [HeiGIT Account](https://account.heigit.org/).
2. Open your account dashboard and copy your API key with openrouteservice access.
   The [HeiGIT API page](https://api.heigit.org/) links to registration and the dashboard.
3. In the local **root `.env` file**, alongside `docker-compose.yml`, set:

   ```dotenv
   ORS_API_KEY=your_key_here
   ```

   Replace `your_key_here` with your own key. Keep the value in `.env.example` blank.
   Django uses this credential on the server; it is not sent to frontend JavaScript.

Continue with Docker setup below. If you add or change the key after starting the
application, run `docker compose up -d --wait web` to apply it. For automatic
loading, fallback and caching behaviour, see [Pedestrian routing](#pedestrian-routing).

### 3. Build the web image, start PostGIS and apply migrations

Run each command in order and check that it succeeds before continuing:

```bash
docker compose config --quiet
docker compose build web
docker compose up -d --wait db
docker compose run --rm -T web python manage.py migrate --noinput
```

The database's first startup creates PostGIS and the restricted application role.
Migrations create the Django tables. The temporary `run --rm` web containers use
that same database and exit after each command.

### 4. Import all four bundled datasets

```bash
mkdir -p data/import-reports
docker compose run --rm -T web python manage.py import_canvas > data/import-reports/canvas.json
docker compose run --rm -T web python manage.py import_public_art --source-srid 4326 > data/import-reports/public_art.json
docker compose run --rm -T web python manage.py import_heritage > data/import-reports/heritage.json
docker compose run --rm -T web python manage.py import_parks > data/import-reports/parks.json
```

In PowerShell, replace the `mkdir -p` line with:

```powershell
New-Item -ItemType Directory -Force -Path data/import-reports | Out-Null
```

Run the same four `docker compose` import commands afterwards.

Each command writes its results to the corresponding local JSON report. No
external dataset downloads are required. The public-art command requires
`--source-srid 4326` to explicitly declare its documented WGS84 interpretation.
After all four complete, expect **922 Places, 484 Parks and four DatasetSources**.
See [Import behaviour](#import-behaviour) for exclusions and repeat-run behaviour.

### 5. Start and check the application

```bash
docker compose up -d --wait
docker compose ps
docker compose exec web python manage.py check
```

This starts Django/Gunicorn and pgAdmin alongside PostGIS. The web container
collects static assets automatically; there is no separate frontend build step.

- DublinQuest: http://localhost:8000/ — choose a start and build a quest.
- Readiness: http://localhost:8000/health/ — expect `{"status":"ok"}`.
- Spatial API: http://localhost:8000/api/places/?format=json — expect count 922.
- pgAdmin: http://localhost:5050/ — use the pgAdmin credentials chosen in `.env`.

The guest application needs no login. `/health/` checks database connectivity and
PostGIS availability; it does not check import counts or certify migrations.

### 6. Optional staff account and database management

To create a staff/superuser account for spatial CRUD:

```bash
docker compose exec web python manage.py createsuperuser
```

Log in at http://localhost:8000/api-auth/login/?next=/api/ to use the authenticated
DRF browsable API. [API.md](API.md) includes temporary-record CRUD examples.
http://localhost:8000/admin/ manages Django accounts; spatial models are managed
through the API. Staff login is not required to generate or save guest quests.

In pgAdmin, register a server with host `db`, port `5432`, maintenance database
matching `POSTGRES_DB`, and the `DATABASE_USER` / `DATABASE_PASSWORD` application
credentials. Use the administrator credentials only for database administration.
Django staff accounts are separate from database and pgAdmin accounts.

## Project structure

- `config/`: settings, root URLs, page view, WSGI and readiness checks.
- `places/`: attractions, park data, imports and spatial APIs.
- `adventures/`: adventure selection, guest ownership, persistence and progress.
- `docker/db/`: first-run SQL that creates a restricted application database role.
- `templates/explore.html`: accessible adventure-builder page.
- `static/`: original CSS/JavaScript and licensed Leaflet/Bootstrap assets; collected output stays inside the web container.

The spatial schema is implemented in `places` and `adventures`; see [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for fields, relationships, CRS handling and database-backed test commands. Migrations are applied explicitly during setup. Dataset import commands are included in the setup guide above; the places/parks endpoints and spatial searches are documented in [API.md](API.md). The frontend uses these same APIs; it does not repeat spatial queries or stop selection in JavaScript.

## Containers and persistence

The three services follow the module's Docker Compose structure. Django connects to `db:5432` over a custom bridge network, using subnet `172.28.40.0/24`. Change `DOCKER_SUBNET` before startup if it conflicts with another local network. Only web and pgAdmin ports are published, bound to the host's loopback address.

PostgreSQL and pgAdmin use named volumes. `docker compose down` keeps their data; **`docker compose down -v` deletes it**. Initialization credentials and the database-role SQL apply only to an empty database volume. Editing `.env` does not change passwords already stored in PostgreSQL or pgAdmin.

The web image runs as a non-root user with Gunicorn. WhiteNoise serves collected static assets without adding an Nginx service. It is a small addition to the labs' static-file setup. Source is copied into the image rather than bind-mounted, so rebuild after changing code, templates, static assets or dependencies:

```bash
docker compose up -d --build --wait
```

Migrations remain a separate explicit step after schema changes. Restarting containers does not reset or seed the database. Secrets and local course materials are excluded from both Git and the Docker build context.

### Apple Silicon

Verified on an Apple Silicon Mac with a `linux/arm64` Docker engine on 2 November 2026. The web image runs natively as ARM64; the PostGIS image runs with explicit `platform: linux/amd64` emulation. PostgreSQL 16.15 and PostGIS 3.6 started successfully, including initialization from an empty temporary database. Database connectivity, an EPSG:4326 → EPSG:2157 GeoDjango transformation and session persistence across container recreation passed.

The database uses `postgis/postgis:16-3.6`, a newer PostGIS version than the labs' 16-3.4 image. Emulation performance has not been benchmarked. Main Python dependencies are pinned in `requirements.txt`; container tags and transitive dependencies may still change on future rebuilds.

## Checks and troubleshooting

```bash
docker compose ps
docker compose logs --tail=100 web db
docker compose exec web python manage.py check
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test config
docker compose exec web python -m pip check
```

To inspect PostGIS:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT PostGIS_Version();"'
```

If a port is occupied, stop the conflicting application or change the published host port in Compose. If database login fails, check the original credentials used to initialize the existing volume. Do not delete volumes as a routine fix. If an interrupted first startup leaves initialization incomplete, inspect the logs before repairing the database.

This setup uses `DEBUG=False`, explicit allowed hosts, CSRF middleware, password validators and restricted database credentials. It is intended for a local demonstration over HTTP. The deployment check reports four HTTPS-related warnings: HSTS, HTTPS redirection and secure session/CSRF cookies. Public hosting would require TLS and appropriate proxy/security configuration; it has not been configured or verified. Guest adventure mutations enforce CSRF protection and session ownership, including for anonymous visitors.

See [FRONTEND_TESTING.md](FRONTEND_TESTING.md) for the browser testing guide, responsive checks and optional automated browser test.

## Data sources

The repository includes four qualified, unmodified Dublin City Council dataset snapshots in `data/raw/` (3.27 MB total). They are third-party open data published under Creative Commons Attribution, separate from my original DublinQuest application code. See [DATA_SOURCES.md](DATA_SOURCES.md) for quality findings, attribution and reproduction commands, and [data/sources.json](data/sources.json) for exact resource URLs and SHA-256 checksums. A fresh clone includes the source files needed by the import commands, without a separate dataset download. The setup guide above populates PostGIS from those local snapshots. No dataset photographs are bundled. Small Leaflet library icons are included separately under their library licence; map tiles are loaded from OpenStreetMap at runtime.

## Import behaviour

The CSV command explicitly declares WGS84 because its source metadata does not specify a datum; this interpretation is recorded in its report. The GeoJSON sources declare CRS84. All stored geometries are transformed to EPSG:2157. No external dataset downloads are needed.

Each command writes a JSON report containing counts and the outcome/reason for every source row. Reports are ignored by Git. The verified baseline is **314 Canvas places, 82 public artworks, 42 heritage places and 484 park boundaries with 484 representative places: 922 places overall**. See [DATA_SOURCES.md](DATA_SOURCES.md) for exclusions and quarantine reasons.

Re-running these commands updates the same source-keyed records rather than creating duplicates. It also restores their imported fields and park representative points, so run imports deliberately if staff have edited imported records. Commands verify the pinned snapshot checksums and run atomically per dataset; they do not erase the database, remove unrelated records, or download/repair source data. Do not update the source manifest to bypass a checksum error without qualifying the changed dataset first.


## Spatial API

Public GeoJSON endpoints provide place/park listings, category filters, proximity searches, park containment and buffered-area intersection. Spatial writes require an active staff account and session CSRF protection. See [API.md](API.md) for endpoints, example requests, expected Dublin results and manual CRUD tests. Interactive API documentation is available at http://localhost:8000/api/docs/.


## Your first adventure

1. Open http://localhost:8000/ and search for **Thomas Moore**, select a popular
   starting point, or click the map. Autocomplete searches imported names only;
   popular shortcuts are separate reference coordinates, not verified entrances.
2. Choose categories, radius and stop count, then build a quest. It saves
   automatically in this browser without an account.
3. Use the map and journey together. Desktop has an independently scrollable
   journey beside the map; mobile places next-stop visit/undo controls below the
   map, with access to the full journey.
4. Mark or undo visits from cards or marker popups. Visited markers retain their
   number with an emerald checkmark; the first unvisited stop has an orange ring
   and arrow. Cards distinguish Next stop, Upcoming and Visited. When all stops
   are marked visited, the Quest complete panel appears.
5. Reopen a quest from Saved adventures to continue. **Edit quest** returns to the
   builder; regeneration applies changes and resets progress after confirmation.
   You can return without applying edits, rename the quest or delete it.

For walking routes, leg colours and caching, see [Pedestrian routing](#pedestrian-routing).

The interface uses local Leaflet 1.9.4 and Bootstrap 5.3.8 assets; no frontend build system is required. OpenStreetMap tiles need internet access. Django sends `Referrer-Policy: strict-origin-when-cross-origin` so tile requests identify the application origin without exposing page paths or query strings; normal browser tile caching is preserved. Scroll-wheel map zoom is disabled to make page scrolling easier; use the map zoom controls, keyboard or touch gestures. A place search provides an alternative to choosing a start by clicking the map.

See [FRONTEND_TESTING.md](FRONTEND_TESTING.md) for the full interface walkthrough, or [API.md](API.md#manual-guide-generate-your-first-adventure) to exercise the underlying APIs directly.

## Pedestrian routing

Walking routes and estimated walking distance/duration require a valid
`ORS_API_KEY` and access to the HeiGIT service. Follow the key setup in
[Running locally](#running-locally). The core application can still generate/save
quests, run spatial searches and record visits without this credential.

Django keeps the key server-side and sends the ordered start/stop coordinates to
HeiGIT. After generation or opening a saved quest, a loading indicator appears
while routing runs in the background; the map and controls remain usable.

A successful response displays a solid pedestrian route with estimated walking
distance/time and hides the dashed sequence. Incoming legs have distinct colours;
a leg turns grey when its destination is marked visited. **Leg colours** lists
numbered legs, and **View straight-line sequence** switches views. Times exclude
visits; source markers stay in place and access/entrances are not verified. Shared
streets can cause legs to overlap visually.

Pending results, successful routes and failures are cached in page memory.
Progress updates, pan/zoom, view toggles and reopening a cached quest do not
request routing again. Regeneration or changed stops invalidate the cache;
reloading the page clears it. A 30-second server-side session cooldown limits
requests. Reload or regenerate later to retry a cached failure.

Missing/invalid credentials, provider errors or unroutable points automatically
restore the dashed sequence without affecting saved quests. This fallback joins
stops directly, regardless of roads, rivers or access: its distances are
straight-line measurements, not walking distances, and it provides no walking
duration. See [routing tests](FRONTEND_TESTING.md#walking-route-verification) and
[API details](API.md#pedestrian-route).

## Project documentation

- [Architecture and request flow](ARCHITECTURE.md)
- [Database schema and spatial indexes](DATABASE_SCHEMA.md)
- [API endpoints and spatial-query demonstrations](API.md)
- [User guide and browser checks](FRONTEND_TESTING.md)
- [Data sources, licences and import decisions](DATA_SOURCES.md)

### Current application screenshots

These captures show the real application, real OpenStreetMap tiles and the no-key
straight-line fallback on a clean local installation. Two stops are marked visited;
no routing geometry or background tiles are mocked in these screenshots.

![Desktop quest journey alongside the interactive Dublin map](screenshots/desktop.png)
![Tablet view with independently scrollable journey](screenshots/tablet.png)
![Mobile map and compact next-discovery controls](screenshots/mobile.png)

### Limitations

- Imported data is historical. Invalid/ambiguous records are quarantined, not silently repaired. The public-art CSV datum is an explicit WGS84 interpretation; dataset licence metadata does not identify a specific CC BY version.
- Guest access depends on the browser session cookie (Django's default expiry is two weeks); clearing or losing it removes access to those quests. The database records are not transferred between browsers.
- Radius measures distance from the start, not total walking distance. Stop order is deterministic and greedy, not an optimal pedestrian tour.
- Walking routes depend on ORS credentials, service availability and mapped access. The [routing section](#pedestrian-routing) explains caching and the straight-line fallback; neither routes nor visit claims verify physical presence.
- OSM imagery and Swagger UI assets need internet access. The normal interface assets and datasets are bundled. No offline tile download is provided.
- This Docker setup is verified for local loopback HTTP. Public cloud hosting and HTTPS are not deployed; see [Checks and troubleshooting](#checks-and-troubleshooting) for the security limitations.
