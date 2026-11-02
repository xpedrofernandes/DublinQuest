# Running, demonstrating and submitting DublinQuest

The brief requires a Brightspace ZIP, a repository link through GitHub Classroom,
and a working demonstration during lab hour. Deadline: **3 November 2026, 23:59**.
It does not specify a ZIP filename, written-report length or presentation duration.
The five-minute walkthrough below is a preparation aid.

## Clean installation

Prerequisites: Docker Desktop/Engine in Linux-container mode, Docker Compose v2,
available ports 8000/5050, and internet access for initial images/dependencies and
map tiles. No host Python/GIS installation or separate dataset download is needed.

```bash
git clone https://github.com/xpedrofernandes/DublinQuest.git
cd DublinQuest
cp .env.example .env
```

Replace every `change-me` value in `.env` with your own random value; use distinct
database administrator/application passwords and usernames. A command such as
`openssl rand -hex 32` generates a secret. Keep `ORS_API_KEY=` empty for the complete
core application with a dashed sequence fallback. Never commit `.env`.

```bash
docker compose config --quiet
docker compose build web
docker compose up -d --wait db
docker compose run --rm -T web python manage.py migrate --noinput
mkdir -p data/import-reports
docker compose run --rm -T web python manage.py import_canvas > data/import-reports/canvas.json
docker compose run --rm -T web python manage.py import_public_art --source-srid 4326 > data/import-reports/public_art.json
docker compose run --rm -T web python manage.py import_heritage > data/import-reports/heritage.json
docker compose run --rm -T web python manage.py import_parks > data/import-reports/parks.json
docker compose up -d --wait
docker compose exec web python manage.py createsuperuser
```

Open `http://localhost:8000/`; `/health/` should return `{"status":"ok"}`. Import
totals must be 922 Places, 484 Parks and four DatasetSources. Register pgAdmin at
`http://localhost:5050/` using the credentials you chose; its database server host
is `db`, not `localhost`. Startup collects static files and runs Gunicorn as a
non-root user. Rebuild after source changes; apply migrations explicitly.

The core guest UI needs no account. To demonstrate staff CRUD, sign in at
`http://localhost:8000/api-auth/login/?next=/api/` with the superuser you just
created. Use the browsable place/park API forms or the exact temporary-record CRUD
examples in [API.md](API.md). Domain models are not registered in Django admin;
`/admin/` manages Django accounts. For assessment, supply your locally created
**demonstration** staff credentials privately if requested. No real passwords,
shared privileged accounts or personal API credentials are distributed in the ZIP.

To enable pedestrian estimates, set your own server-only `ORS_API_KEY` and run
`docker compose up -d --wait web`. This is optional: no credential is needed to
generate, save, progress, regenerate or delete quests. See README/API for the
coordinate-sharing notice, 30-second cooldown, failure handling and limitations.

### Optional remote Docker host — instructions, not a verified deployment

Local deployment is explicitly sufficient. The same installation commands can be
used on a Linux VM with Docker/Compose and repository access. Keep the existing
loopback bindings. From your laptop, tunnel the application instead of exposing
its HTTP port publicly:

```bash
ssh -L 8000:127.0.0.1:8000 -L 5050:127.0.0.1:5050 YOUR_VM_USER@YOUR_VM_HOST
```

Then browse the same localhost URLs. The SSH host/user are placeholders, not an
existing deployment. This has not been tested on a cloud VM. A public website
would need a real domain, TLS/reverse proxy, explicit allowed hosts and CSRF
origins, HTTPS redirects/HSTS, secure cookies, firewall, backup/monitoring and a
review of secrets and routing limits. Those are not configured or claimed here.
The four HTTPS warnings on local `check --deploy` are documented, not silenced.

## Automated verification

Run tests against the separate prepared test database, never a renamed production
database. The script installs PostGIS there without granting CREATEDB/superuser to
the runtime role:

```bash
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < scripts/create_test_database.sql
docker compose run --rm -T web python manage.py test places adventures config --keepdb
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python -m pip check
docker compose exec web python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
```

Optional Chrome/Playwright scripts and their runner setup are in
[FRONTEND_TESTING.md](FRONTEND_TESTING.md). They mock routing and map tiles to avoid
provider traffic. Real map imagery requires a separate visible browser check.
`docker compose down` preserves named volumes; **do not use `down -v` on a database
you want to retain**. Import reruns deliberately restore source fields after staff
edits, so avoid rerunning them on edited data without review.

## Five-minute demonstration

| Time | Show and explain |
|---|---|
| 0:00–0:40 | “DublinQuest builds a personal Dublin exploration quest from real open data.” Choose Trinity as a reference start, explain imported-place autocomplete/map-click alternatives, choose four categories, 2 km and five stops. Generate and show the same-origin API request. |
| 0:40–1:30 | Show the map beside the journey, numbered/category markers, start and search polygon. Mark stops 1 and 3 from popup/card, show checkmarks, next stop 2, progress and grey incoming legs when walking is available. Undo a visit. Explain self-reporting, estimated walking time and unchanged source markers. If ORS is unavailable, show the clearly labelled dashed fallback. |
| 1:30–2:30 | Open Spatial tools: nearby places (`ST_DWithin`), overlapping parks (`ST_Buffer` + `ST_Intersects`), then search Merrion Square and find its nine artworks (`ST_CoveredBy`, including boundary points). Explain metres in 2157 and `[lng,lat]` output in 4326. |
| 2:30–3:20 | Show schema diagram and GiST indexes. Explain source-key uniqueness/idempotent imports, quarantined invalid data, park point-on-surface versus entrances, deterministic category variety and nearest-next ordering. Show generated LineString creation and regeneration, not just a static source line. |
| 3:20–4:10 | Reopen the saved quest; show persistence. In a separate private window, explain the empty guest list/foreign-ID 404. Show validation and anonymous-write rejection, then staff Point/MultiPolygon CRUD using temporary records only. Regeneration updates line/search area/stops atomically; delete the temporary quest to demonstrate line deletion. |
| 4:10–5:00 | Show three Docker services, custom subnet/volumes, health and tests. Explain restricted database role, server-only ORS key and local HTTP limitations. Finish with reproducible setup, data/library attribution and the main known limitations. |

Practise this with the actual browser before the lab. Keep `/api/` and pgAdmin
ready, but do not display `.env`, resolved Compose environment or shell history
containing credentials. A session cookie is required to reopen a guest quest.

## Final submission checklist — actions for the student

- [ ] Review [FINAL_AUDIT.md](FINAL_AUDIT.md), screenshots and the working app.
- [ ] Accept the instructor's GitHub Classroom invitation and submit the correct repository link there. The personal repository alone does not establish Classroom compliance.
- [ ] Make the repository public **or** grant the instructor access and confirm acceptance. Neither access nor Classroom enrolment has been verified in this audit.
- [ ] Push approved local commits manually; check the GitHub file view matches the intended revision.
- [ ] Upload `dist/DublinQuest.zip` to Brightspace and verify the upload/receipt. Keep the ZIP name/course identifier consistent with any additional Brightspace instructions.
- [ ] Submit the required GitHub link via Classroom and the learning-management submission as instructed. Current origin: `https://github.com/xpedrofernandes/DublinQuest.git`.
- [ ] Check any additional module rules for permitted assistance/attribution and ensure any required declarations are accurate. The supplied brief requires individual development and attribution of external snippets/libraries; it does not specify an assistance-disclosure template.
- [ ] Provide demonstration-only staff credentials privately if needed, or create them with the assessor. Keep real secrets out of the archive/repository.
- [ ] Bring the running laptop to lab hour, check Docker, map connectivity and the guest workflow, and have a no-key fallback ready. Local URL: `http://localhost:8000/` (accessible on that laptop, not the lecturer's machine over the network).
- [ ] Check the deadline: **3 November 2026, 23:59**. The brief's late-policy text is an unfilled placeholder; consult the official institutional/module policy rather than assuming a grace period.

## Rebuilding the submission ZIP

After committing the final reviewed source and screenshots:

```bash
mkdir -p dist
git archive --format=zip --prefix=DublinQuest/ --output=dist/DublinQuest.zip HEAD
```

This includes committed application source, dependencies, Compose/Docker files,
migrations, documentation, library licences, screenshots and exactly four raw
datasets. It excludes `.git`, ignored `.env`, course/private materials, database
volumes, caches, generated import reports and temporary browser tooling. Inspect
the archive before upload. The archive deliberately omits Git history; the
Classroom repository supplies that history. A ZIP of an older commit will omit
later work, so regenerate it after any subsequent approved commit.
