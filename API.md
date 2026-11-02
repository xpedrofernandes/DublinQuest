# DublinQuest API

The places/parks REST API provides staff spatial CRUD and three spatial searches. Adventure generation, guest-owned adventure endpoints and progress updates are not yet available; LineString creation/regeneration is not implemented by the endpoints below. No frontend map has been added yet.

## Contract

Base URL: `http://localhost:8000/api/`. Public reads; writes require an active Django staff account authenticated with a Django session and a valid CSRF token. Basic/token authentication and cross-origin access are not enabled. Log in at `/api-auth/login/?next=/api/` using your own staff/superuser credentials.

All API geometries are 2D GeoJSON in EPSG:4326, `[longitude, latitude]`. Input bodies contain a Point or MultiPolygon geometry, not WKT/EWKT or a custom CRS declaration. The serializer validates type, finite coordinate ranges and GEOS validity, then transforms to EPSG:2157. Read serialization transforms a clone back to 4326, preserving the stored/in-memory model geometry. Park representatives are points-on-surface, not verified entrances.

Reads return Features and paginated FeatureCollections:

```json
{"type":"FeatureCollection","count":922,"next":"...","previous":null,"features":[{"id":1,"type":"Feature","geometry":{"type":"Point","coordinates":[-6.26,53.35]},"properties":{"name":"..."}}]}
```

This is an abbreviated shape example, not an asserted real source feature. The root `features` is an array, never another FeatureCollection. Default page size is 50, maximum 100. `count` covers all matching rows; the frontend must follow `next` instead of treating the first page as the whole result. Point properties include nullable `distance_m` (populated on proximity results), category, source attribution and immutable source key. Imported source/checksum links identify the original snapshot, not a hash of a staff-edited record. Newly created staff records have `source: null` and a server-generated `staff:<UUID>` key, avoiding false external attribution.

Write bodies are ordinary JSON objects, rather than GeoJSON Features. POST creates (201), PUT replaces required fields (200), PATCH partially updates (200), DELETE removes (204). Unsupported or server-managed write fields are rejected, including source, source_key, park and id. Source attribution cannot be reassigned through these endpoints. Invalid fields return 400; anonymous/nonstaff writes and missing/incorrect staff CSRF tokens return 403; missing/hidden records return 404; deletion of attractions used by saved adventures returns 409. Conflict responses do not expose database error details.

## Endpoints

| Method/path | Purpose and accepted search parameters |
|---|---|
| GET `/categories/` | Four category values and display labels |
| GET `/places/` | List/filter using `categories`, `search`, `page`, `page_size` |
| POST `/places/` | Create a staff-managed Point; fields name, category, point; optional description, artist, profile_url, active |
| GET/PUT/PATCH/DELETE `/places/{id}/` | Retrieve/update/delete a standalone place |
| GET `/places/nearby/` | Proximity: required lat/lng; optional radius_m, categories, search, page, page_size |
| GET/POST `/parks/` | List/create MultiPolygon parks; list parameters search, page, page_size; create fields name/boundary, optional typology/active |
| GET/PUT/PATCH/DELETE `/parks/{id}/` | Retrieve/update/delete a park and synchronize its representative Place |
| GET `/parks/{id}/places/` | Containment: active non-park attractions covered by this park; optional categories, search, page, page_size |
| GET `/parks/intersecting/` | Parks intersecting a PostGIS search buffer; required lat/lng; optional radius_m, search, page, page_size |
| GET `/schema/` | OpenAPI schema |
| GET `/docs/` | Swagger UI (its UI assets require internet access) |

`categories` is a comma-separated list of distinct values: `street_art,public_art,heritage,park`. Blank/unknown/duplicate categories are invalid. `lat` is -90..90, `lng` is -180..180; coordinates must be finite and transformable to EPSG:2157. Radius is an integer 250..5000 metres, default 2000. Search text is nonblank, at most 100 characters. Unsupported/repeated parameters and invalid page sizes return 400. A page beyond available results returns 404. DRF's standard `format=json` parameter and `.json` suffix are supported.

Public listings/details exclude inactive places/parks; inactive park representatives are hidden too. Staff can read inactive records for management. Park containment returns active non-park attractions, excluding the park's own derived representative point. Proximity includes a record at the origin if it matches; future adventure generation must explicitly exclude coincident origin stops.

Direct writes/deletes of park representative places are rejected. Manage the park instead: creating a boundary creates its Place; boundary/name/active updates synchronize that Place atomically; park deletion removes it unless saved-adventure references prevent deletion. Invalid boundaries are rejected, never silently repaired. Re-running an import can restore imported fields after staff edits, as documented in README.

## Spatial operations and index evidence

| User operation | GeoDjango/PostGIS implementation | Meaning and limits |
|---|---|---|
| Find nearby places | `point__dwithin` → `ST_DWithin`; `Distance` annotation/order | Metre radius with inclusive boundary; nearest-first order, PK tie-break; distance is straight-line |
| Explore a park's contents | `point__coveredby=park.boundary` → `ST_CoveredBy` | Boundary-inclusive containment, equivalent to reversing `ST_Covers`; strict `ST_Contains` would exclude boundary points |
| Find parks overlapping the search area | Parameterized `ST_Buffer` on the projected origin, then `boundary__intersects` → `ST_Intersects` | Actual database-generated polygon, not a bounding-box filter or browser-only circle; includes touching boundaries |

The intersection response additionally contains `search_area`, an EPSG:4326 Polygon for Leaflet. PostGIS's default buffer approximates a circle with straight segments, so this polygon is the exact intersection contract; it is not a mathematically perfect geodesic circle. Proximity uses `ST_DWithin` directly rather than that approximation.

These are three independently callable, meaningful spatial queries for the assignment. Their obvious frontend controls will be implemented later. The implementation is conventional viewsets/serializers/ORM; the small parameterized SQL helper constructs the PostGIS buffer. It interpolates no SQL from user text. Indexed geometry columns stay in EPSG:2157; input parameters are transformed before filtering, preserving GiST usability. Only response copies transform to 4326.

EXPLAIN checks against the imported data on 2 November 2026 showed bitmap index scans on the Place point GiST index for 1 km proximity (93 matches) and Merrion containment (9), and on the Park boundary GiST index for 1 km intersection (27). Exact filters follow the index bounding-box prefilter. Distance sorting still needs a sort. Plans depend on table statistics/radius; do not claim every query must use an index or that these counts are a performance benchmark.

## Manual testing guide — places/parks milestone

After rebuilding/applying migrations (`docker compose build web`, `docker compose run --rm web python manage.py migrate --noinput`, `docker compose up -d --wait web`), use an anonymous/private browser window for these baseline reads. Counts assume the qualified data before manual edits.

| Exact URL | Expected |
|---|---|
| `http://localhost:8000/health/` | 200, `{"status":"ok"}` |
| `http://localhost:8000/api/categories/?format=json` | 200, four categories |
| `http://localhost:8000/api/places/?format=json` | 200, count 922, 50 Features and a next-page URL |
| `http://localhost:8000/api/parks/?format=json` | 200, count 484 |
| `http://localhost:8000/api/places/nearby/?lat=53.35&lng=-6.26&radius_m=2000&format=json` | 200, count 224; nearest is James Joyce Statue, approximately 16.13 m |
| `http://localhost:8000/api/places/nearby/?lat=53.35&lng=-6.26&radius_m=2000&categories=public_art&format=json` | 200, count 63, nearest-first distances |
| `http://localhost:8000/api/parks/?search=Merrion%20Square&format=json` | 200, one park; note its returned ID |
| `http://localhost:8000/api/parks/313/places/?categories=public_art&format=json` | 200, nine artworks; 313 is the current database ID, replace with the ID discovered above on another database |
| `http://localhost:8000/api/parks/intersecting/?lat=53.35&lng=-6.26&radius_m=2000&format=json` | 200, count 55 and a search_area Polygon |
| `http://localhost:8000/api/places/nearby/?lat=91&lng=-6.26&radius_m=2000&format=json` | 400, coordinate validation error |
| `http://localhost:8000/api/places/nearby/?lat=53.35&lng=-6.26&radius_m=-1&format=json` | 400, radius validation error |
| `http://localhost:8000/api/places/?categories=unknown&format=json` | 400, category validation error |
| `http://localhost:8000/api/places/?page_size=101&format=json` | 400, page-size validation error |

Verify Feature coordinates look like longitude -6.x / latitude 53.x, distances increase, `features` is an array, and following `next` gives another page. Individual place/park IDs can be followed through their detail URLs. An empty valid search is 200 with count 0 and features [], not a server error. These checks do not yet draw a Leaflet map.

An anonymous write must fail before creating anything:

```bash
curl -i -X POST http://localhost:8000/api/places/ -H 'Content-Type: application/json' -d '{}'
```

Expected 403 with a JSON detail. To check staff CRUD, sign in through `http://localhost:8000/api-auth/login/?next=/api/` with your own staff credentials, then run the following in that page's browser console. The synthetic test record must be deleted; do not change imported attractions for this test.

```javascript
window.dqApi = async (url, method, body) => {
  const token = document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.split('=')[1];
  const response = await fetch(url, {method, headers: {'Content-Type': 'application/json', 'X-CSRFToken': token}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = response.status === 204 ? null : await response.json();
  console.log(response.status, data);
  if (!response.ok) throw new Error('Request failed; inspect the response above');
  return data;
};
window.dqTestPlace = await dqApi('/api/places/', 'POST', {name: 'Temporary API test place (delete)', category: 'heritage', point: {type: 'Point', coordinates: [-6.26, 53.35]}});
await dqApi(`/api/places/${dqTestPlace.id}/`, 'GET');
await dqApi(`/api/places/${dqTestPlace.id}/`, 'PATCH', {point: {type: 'Point', coordinates: [-6.25, 53.35]}});
await dqApi(`/api/places/${dqTestPlace.id}/`, 'DELETE');
```

Expected statuses: 201, 200, 200, 204; PATCH returns longitude approximately -6.25. `source` remains null and the server assigns a staff key. Without the CSRF header a logged-in write must return 403. Nonstaff accounts must also receive 403 even with a valid CSRF token.

A temporary polygon CRUD test, using the same helper:

```javascript
window.dqTestPark = await dqApi('/api/parks/', 'POST', {name: 'Temporary API test park (delete)', boundary: {type: 'MultiPolygon', coordinates: [[[[-6.26,53.35],[-6.259,53.35],[-6.259,53.351],[-6.26,53.351],[-6.26,53.35]]]]}});
await dqApi(`/api/parks/${dqTestPark.id}/`, 'PATCH', {name: 'Renamed temporary API test park'});
await dqApi(`/api/places/?search=Renamed%20temporary%20API%20test%20park`, 'GET');
await dqApi(`/api/parks/${dqTestPark.id}/`, 'DELETE');
```

Expected 201, 200, a collection with one synchronized representative Place, then 204. That representative Place must disappear after deleting the park. A self-intersecting MultiPolygon must return 400. Deleting a Place already used by an AdventureStop is automatically tested to return 409; end-user adventure creation will be available in the next milestone.

Automated verification: `docker compose run --rm web python manage.py test places adventures config --keepdb`; provision the separate test database first as described in DATABASE_SCHEMA.md. Tests check metric/boundary accuracy, touching/intersection-vs-bbox behavior, pagination/GeoJSON, malformed input, source-field protection, nonstaff/anonymous denial, session CSRF and synchronized CRUD. Swagger is at `/api/docs/`, with machine-readable schema `/api/schema/`.
