# DublinQuest — Explore Dublin Your Way

DublinQuest is an individual final-year Advanced Web Mapping coursework project at TU Dublin. It will let visitors build personalised Dublin exploration adventures from real geographic data, then view their stops and record progress on an interactive map.

## Development status

Phase 0 is in progress. This first increment establishes the repository and excludes local coursework materials and secrets. **The application and Docker configuration have not been implemented yet.** There are currently no application setup commands or passing application tests to report.

Development takes place on Windows; the assessment deployment will run on an Apple Silicon Mac. Docker/PostGIS compatibility must be verified on that Mac early in Phase 0, rather than assumed from Windows results.

## Planned scope

- Django, GeoDjango and Django REST Framework backed by PostgreSQL/PostGIS.
- Leaflet and OpenStreetMap with HTML, CSS, JavaScript and Bootstrap 5.
- Docker Compose services for Django, PostGIS and pgAdmin, with persistent volumes and a custom network subnet.
- Real point and polygon datasets, spatial CRUD, and independently demonstrable proximity, containment and buffered-intersection queries.
- Guest-owned saved adventures, generated sequence LineStrings and manually recorded visited stops.
- Staff-only management, input validation and CSRF protection for guest mutations.

Connecting lines will represent a suggested exploration sequence, not verified pedestrian navigation. AI integration, GPS tracking and turn-by-turn routing are outside the initial scope.

## Repository boundaries

The following local folders are intentionally excluded from version control and must remain on the developer's machine:

- `assignment/`
- `course-materials/`
- `docs/`
- `microsoft/` / `Microsoft/`

Public project documentation will be maintained at the repository root as the relevant implementation is completed. Local secrets, environments, database-volume directories and generated caches are also excluded. A future `.env.example` will contain placeholders only.

## Development and submission workflow

Changes are developed and checked in small logical increments using descriptive conventional commits. Commits are made locally; **the student manually executes every push**. No automated publishing or deployment is configured.

The current repository is a personal private repository, not a confirmed GitHub Classroom assignment repository. The student must confirm the submission route and grant the instructor access, or use the Classroom repository if one is subsequently provided. Submission also requires the specified Brightspace package and lab demonstration.

This is original individual coursework. External datasets, libraries and adapted examples must be attributed, and the student must understand and be able to explain the implementation.
