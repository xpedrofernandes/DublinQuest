# DublinQuest

### Explore Dublin Your Way

DublinQuest is a location-based exploration app I'm developing for CMPU4058 — Advanced Web Mapping at TU Dublin. The idea is to help people discover Dublin through its street art, historic landmarks, public artworks and parks.

Instead of following a fixed tour, you choose where to start, what interests you, how far to explore and how many places to visit. DublinQuest will use those choices to put together an adventure on an interactive map.

## How it will work

1. Choose a starting place or click a location on the map.
2. Select your interests, a search radius and the number of stops.
3. Explore the suggested stops using the map and an ordered list of places.
4. Mark stops as visited and keep track of your progress.

The map will show the starting point, search area, numbered stops and a suggested sequence connecting them. Each stop will include a description, category and distance information.

The connecting lines will show the suggested order of exploration, not walking directions. Distances will be straight-line estimates.

## Web mapping

The project will use real Dublin open data stored in PostgreSQL/PostGIS. Its spatial features will include:

- Finding places within a chosen radius.
- Finding attractions inside a park's boundary.
- Finding parks and open spaces that overlap the search area.
- Storing places as points, park boundaries as polygons and adventure sequences as lines.
- Creating, viewing, editing and deleting spatial records through a staff management interface.

Adventures and visited stops will be saved for the same browser, without requiring a visitor account.

## Technology stack

- **Backend:** Python, Django, GeoDjango and Django REST Framework
- **Database:** PostgreSQL with PostGIS
- **Map:** Leaflet.js and OpenStreetMap
- **Frontend:** HTML, CSS, JavaScript and Bootstrap 5
- **Local deployment:** Docker Compose and pgAdmin

## Scope

The initial version focuses on spatial searches, interactive mapping and a complete exploration flow. It won't include live GPS tracking, turn-by-turn navigation or an AI assistant.

The container foundation is running. Adventure features, dataset imports and the map are still to be implemented.

## Running locally

Docker Desktop with Docker Compose is required. No host Python, PostgreSQL or GIS installation is needed.

```bash
cp .env.example .env
```

Edit `.env` and replace all `change-me` values with different random passwords and a long Django secret key. `openssl rand -hex 32` can generate each value. Keep `.env` private. The database administrator and application use separate accounts; keep their usernames different.

```bash
docker compose config --quiet
docker compose build web
docker compose up -d --wait db
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --wait
docker compose exec web python manage.py createsuperuser
```

- Readiness: http://localhost:8000/health/
- Django administration: http://localhost:8000/admin/
- pgAdmin: http://localhost:5050/ — sign in with the pgAdmin credentials in `.env`.

In pgAdmin, register a server with host `db`, port `5432`, maintenance database matching `POSTGRES_DB`, and the `DATABASE_USER` / `DATABASE_PASSWORD` application credentials. Use the administrator credentials only for database administration. Django staff accounts are separate from both database and pgAdmin accounts.

The root URL has no application page yet. `/health/` checks database connectivity and PostGIS availability; it returns JSON with HTTP 200 when ready or 503 when unavailable. It does not certify that migrations have been applied.

## Project structure

- `config/`: settings, root URLs, WSGI and readiness checks.
- `places/`: app reserved for attractions and park data.
- `adventures/`: app reserved for saved exploration adventures and progress.
- `docker/db/`: first-run SQL that creates a restricted application database role.
- `static/`: source assets; collected output stays inside the web container.

The apps currently have no domain models. Django's built-in authentication, administration and session migrations are applied explicitly during setup.

## Containers and persistence

The three services follow the module's Docker Compose structure. Django connects to `db:5432` over a custom bridge network, using subnet `172.28.40.0/24`. Change `DOCKER_SUBNET` before startup if it conflicts with another local network. Only web and pgAdmin ports are published, bound to the host's loopback address.

PostgreSQL and pgAdmin use named volumes. `docker compose down` keeps their data; **`docker compose down -v` deletes it**. Initialization credentials and the database-role SQL apply only to an empty database volume. Editing `.env` does not change passwords already stored in PostgreSQL or pgAdmin.

The web image runs as a non-root user with Gunicorn. WhiteNoise serves collected static assets without adding an Nginx service. It is a small addition to the labs' static-file setup. Source is copied into the image rather than bind-mounted, so rebuild after changing Python code or dependencies:

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

This setup uses `DEBUG=False`, explicit allowed hosts, CSRF middleware, password validators and restricted database credentials. It is intended for a local demonstration over HTTP. The deployment check reports four HTTPS-related warnings: HSTS, HTTPS redirection and secure session/CSRF cookies. Public hosting would require TLS and appropriate proxy/security configuration; it has not been configured or verified. Anonymous adventure mutation protection and ownership checks will be implemented with those endpoints.

Screenshots, data attribution, API documentation and the user guide will be added as the corresponding features are completed.

## Data sources

The four Dublin open-data snapshots have been downloaded and inspected locally. See [DATA_SOURCES.md](DATA_SOURCES.md) for quality findings, attribution and reproduction commands, and [data/sources.json](data/sources.json) for exact resource URLs and SHA-256 checksums. Raw downloads stay outside Git. No attraction data has been imported yet.
