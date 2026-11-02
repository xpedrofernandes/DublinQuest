# DublinQuest API

The places/parks REST API provides staff spatial CRUD and three spatial searches. Guest adventure generation, ownership, progress and LineString creation/regeneration are described in the adventure section below. The Leaflet interface is available at `/`; see [FRONTEND_TESTING.md](FRONTEND_TESTING.md) for its browser walkthrough.

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

Public listings/details exclude inactive places/parks; inactive park representatives are hidden too. Staff can read inactive records for management. Park containment returns active non-park attractions, excluding the park's own derived representative point. Proximity includes a record at the origin if it matches; adventure generation explicitly excludes coincident origin stops.

Direct writes/deletes of park representative places are rejected. Manage the park instead: creating a boundary creates its Place; boundary/name/active updates synchronize that Place atomically; park deletion removes it unless saved-adventure references prevent deletion. Invalid boundaries are rejected, never silently repaired. Re-running an import can restore imported fields after staff edits, as documented in README.

## Spatial operations and index evidence

| User operation | GeoDjango/PostGIS implementation | Meaning and limits |
|---|---|---|
| Find nearby places | `point__dwithin` → `ST_DWithin`; `Distance` annotation/order | Metre radius with inclusive boundary; nearest-first order, PK tie-break; distance is straight-line |
| Explore a park's contents | `point__coveredby=park.boundary` → `ST_CoveredBy` | Boundary-inclusive containment, equivalent to reversing `ST_Covers`; strict `ST_Contains` would exclude boundary points |
| Find parks overlapping the search area | Parameterized `ST_Buffer` on the projected origin, then `boundary__intersects` → `ST_Intersects` | Actual database-generated polygon, not a bounding-box filter or browser-only circle; includes touching boundaries |

The intersection response additionally contains `search_area`, an EPSG:4326 Polygon for Leaflet. PostGIS's default buffer approximates a circle with straight segments, so this polygon is the exact intersection contract; it is not a mathematically perfect geodesic circle. Proximity uses `ST_DWithin` directly rather than that approximation.

These are three independently callable, meaningful spatial queries for the assignment. The frontend exposes them as Find nearby places, Find parks overlapping radius, and Find places inside a park. The implementation is conventional viewsets/serializers/ORM; the small parameterized SQL helper constructs the PostGIS buffer. It interpolates no SQL from user text. Indexed geometry columns stay in EPSG:2157; input parameters are transformed before filtering, preserving GiST usability. Only response copies transform to 4326.

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

Expected 201, 200, a collection with one synchronized representative Place, then 204. That representative Place must disappear after deleting the park. A self-intersecting MultiPolygon must return 400. Deleting a Place already used by an AdventureStop is automatically tested to return 409; guest adventure creation is available in the adventure section below.

Automated verification: `docker compose run --rm web python manage.py test places adventures config --keepdb`; provision the separate test database first as described in DATABASE_SCHEMA.md. Tests check metric/boundary accuracy, touching/intersection-vs-bbox behavior, pagination/GeoJSON, malformed input, source-field protection, nonstaff/anonymous denial, session CSRF and synchronized CRUD. Swagger is at `/api/docs/`, with machine-readable schema `/api/schema/`.


## Guest adventure API

No account or staff login is required. `GET /api/session/` establishes a database-backed Django session and returns a masked `csrfToken`; the browser stores its HttpOnly session cookie. Every guest POST/PATCH/DELETE enforces Django CSRF, including anonymous requests. Send that token in `X-CSRFToken` with the same session/CSRF cookies. Login is not the ownership mechanism: each browser session has a server-generated guest owner UUID, never accepted from a request body or returned in adventure responses. Staff cannot use this API to read another guest's adventures.

| Method/path (under `/api/`) | Body and result |
|---|---|
| GET `session/` | Initialize/reuse guest session; returns `{"csrfToken":"..."}` |
| POST `adventures/` | Generate and save; required lat/lng/categories; optional title, radius_m (2000), stop_count (5); returns 201 |
| GET `adventures/` | Current guest's saved adventures; count/next/previous/results pagination, default 10 / maximum 50; optional search/page/page_size |
| GET `adventures/{id}/` | One owned adventure and ordered stops, 200; missing or another guest's ID is 404 |
| PATCH `adventures/{id}/` | Rename only: `{"title":"New title"}`; keeps geometry/visited progress |
| PATCH `adventures/{id}/stops/{stop_id}/` | `{"visited":true}` or false; returns updated full adventure/progress |
| POST `adventures/{id}/regenerate/` | Optional changed generation fields; omitted values use existing criteria. Empty `{}` reruns the same criteria. Requires `confirm_reset:true` if any stop has been visited |
| DELETE `adventures/{id}/` | Delete own adventure/stops, 204; does not delete any source Place/Park |

Generation validation uses the existing spatial API's finite/range/transformation checks. Radius: 250–5000 metres, desired stops: 1–10, one to four distinct supported category codes, nonblank title up to 120 characters. Unknown/server-owned fields, malformed input and no eligible results return HTTP 400. A valid request with fewer eligible locations saves the available stops and returns a warning; it never silently widens the radius. At least one stop is required to save a nonempty LineString. Missing/invalid CSRF returns HTTP 403 before mutation. A stop belonging to a different adventure returns HTTP 404 even if both adventures belong to the same guest. PUT is not supported: use PATCH to rename or POST regenerate to change criteria.

Responses contain UUID id, title, start Point, radius_m, categories, requested_stops, search_area Polygon, path LineString, stops, progress, warnings, total_distance_m and sequence_notice. Geometry is EPSG:4326 GeoJSON, with 2157 storage. Every stop has id, position, a source-attributed Place Feature, straight-line distances from the start/previous stop, visited boolean and visited_at. The embedded Place's nullable distance_m remains the place API's optional annotation; use the explicit stop distance fields here. No owner UUID is exposed.

Progress uses actual saved stop count: `{"visited":1,"total":5,"percent":20.0,"complete":false}`. Repeated visited=true preserves its original timestamp; false clears it. Completion means all actual stops are visited, including a shorter adventure saved with a warning. Rename preserves progress. Successful regeneration keeps adventure UUID/owner but replaces stop IDs, recomputes geometry/distances and resets visits; old stop URLs then return404. Failed regeneration leaves the previous adventure/stops/progress intact. Mutation transactions lock the owned Adventure row to serialize progress/regeneration/deletion on that adventure. Responses are private/no-store.

### Selection algorithm

`adventures/generation.py` reuses the indexed PostGIS proximity search, active/category filters and park-active exclusion. Candidates are nearest-first with PK tie-breaking. It excludes a location coincident with the start within 1 mm and deduplicates candidate coordinates at millimetre precision for selection only; original data/coordinates are not edited.

It reserves the nearest candidate of each available category; if there are fewer requested slots than categories, categories with nearer representatives win. Remaining slots take the nearest unused candidates. It then orders at most ten selected places using a simple greedy nearest-next distance, with PK tie-breaking. The starting point and ordered stop coordinates form the stored LineString; PostGIS constructs the stored search buffer. Identical criteria and unchanged database records give the same stop selection/order, independent of category-input order or session identity. This is understandable category variety plus proximity, not optimal route planning, walking navigation, travel time or access verification. Distances from the origin need not increase along the nearest-next sequence.

No new models or dependencies were introduced. Search radius applies to distance from the start, not to total sequence length. Geometry/distances describe generation time; related Place metadata is live. If staff later move a source Place, regenerate the adventure to refresh its sequence/distances. The saved LineString is not silently rewritten by staff place edits. Park representative points remain explicitly labelled as not verified entrances.

Sessions persist across requests/container restarts using the existing database volume. Two tabs sharing the session share adventures. Clearing browser cookies, session expiry, Django logout (which flushes the session), or switching browser profiles loses access; there is no account recovery or cross-browser sharing in this scope. CSRF bootstrap must be repeated after a login rotates its token. There is no separate unsaved preview endpoint: POST generation saves immediately.

### Manual guide: generate your first adventure

1. Open `http://localhost:8000/api/session/?format=json` in your normal browser. A csrfToken should appear. No login is needed.
2. Open developer tools and select Console (Chrome/Edge on macOS: Cmd+Option+J). Keep the page on localhost:8000 so the requests below use the same cookies.
3. Paste the following block. It obtains a fresh token, defines a small request helper and generates a five-stop adventure.

```javascript
window.dqGuest = await fetch('/api/session/', {cache: 'no-store', credentials: 'same-origin'}).then(r => r.json());
window.dqQuestApi = async (url, method = 'GET', body) => {
  const response = await fetch(url, {method, cache: 'no-store', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': dqGuest.csrfToken}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = response.status === 204 ? null : await response.json();
  console.log(response.status, data);
  if (!response.ok) throw new Error('Inspect the response above before continuing');
  return data;
};
window.dqAdventure = await dqQuestApi('/api/adventures/', 'POST', {
  title: 'College Green discovery',
  lat: 53.34516502,
  lng: -6.258924007,
  categories: ['street_art', 'heritage', 'public_art', 'park'],
  radius_m: 2000,
  stop_count: 5
});
console.table(dqAdventure.stops.map(s => ({position: s.position, name: s.place.properties.name, category: s.place.properties.category, fromStartMetres: s.distance_from_start_m, fromPreviousMetres: s.distance_from_previous_m})));
```

The starting coordinates are copied from the imported Thomas Moore Statue point near Trinity/College Green, not the quarantined Trinity point and not a verified campus entrance. Check the source using `http://localhost:8000/api/places/?search=Thomas%20Moore%20Statue&format=json`.

Expected: HTTP 201, five distinct stops with positions 1–5, coverage of all four categories for this example, requested_stops: 5, radius_m: 2000, progress 0/5, and a LineString with six coordinate pairs (origin plus five stops). Each distance_from_start_m should be at most 2000 metres. Thomas Moore Statue itself is excluded as coincident with the origin. Every stop's source metadata points back to the bundled dataset; parks carry a representative-point warning. `sequence_notice` explicitly rejects pedestrian-routing claims. With the unchanged bundled data, the observed sequence is Normal People (street art), Henry Grattan Statue (public art), Stein Sculpture (public art), Georges Quay (park representative) and Hapenny Bridge (heritage). These names preserve the source spelling. Copy the returned adventure UUID for later retrieval.

List and retrieve it, then reload the browser page and verify the same UUID is still listed:

```javascript
await dqQuestApi('/api/adventures/');
await dqQuestApi(`/api/adventures/${dqAdventure.id}/`);
```

After reload, redefine the helper/bootstrap block if the console variables were lost; use the existing UUID or recover it from `http://localhost:8000/api/adventures/?format=json`. Do not re-run the POST unless you want another saved adventure. The literal retrieval URL is `http://localhost:8000/api/adventures/ADVENTURE_UUID/?format=json`, replacing ADVENTURE_UUID with your returned id.

Visit and unvisit a stop:

```javascript
await dqQuestApi(`/api/adventures/${dqAdventure.id}/stops/${dqAdventure.stops[0].id}/`, 'PATCH', {visited: true});
await dqQuestApi(`/api/adventures/${dqAdventure.id}/`);
await dqQuestApi(`/api/adventures/${dqAdventure.id}/stops/${dqAdventure.stops[0].id}/`, 'PATCH', {visited: false});
```

Expected progress 1/5 (20%) then 0/5, with visited_at populated then cleared. Mark all five visited to see complete=true and 100%; this is the backend completion state, not a graphical completion screen yet.

Rename without resetting progress, then regenerate with explicit reset confirmation:

```javascript
await dqQuestApi(`/api/adventures/${dqAdventure.id}/`, 'PATCH', {title: 'My first DublinQuest'});
window.dqAdventure = await dqQuestApi(`/api/adventures/${dqAdventure.id}/regenerate/`, 'POST', {categories: ['heritage', 'public_art'], stop_count: 3, confirm_reset: true});
```

Expected HTTP 200, same adventure UUID, three newly numbered stops/new stop IDs, a four-vertex LineString and progress 0/3. Use the updated dqAdventure.stops from now on. If a stop was visited, omitting confirm_reset must return HTTP 400; the previous adventure remains intact. Supplying an impossible search (e.g. lat54/lng-7/radius250) also returns HTTP 400 without destroying the prior adventure.

For ownership, open a separate browser profile or a private window independent of your original normal window. Visit `/api/session/?format=json` there, then open your original adventure's exact retrieval URL: expect HTTP 404, while `/api/adventures/?format=json` is empty. New private windows can share cookies with other private windows; two tabs in the same session are not independent guests. Never copy cookies between the sessions.

To check anonymous CSRF, in your original console omit the CSRF header:

```javascript
console.log((await fetch(`/api/adventures/${dqAdventure.id}/`, {method: 'DELETE', credentials: 'same-origin'})).status);
```

Expected HTTP 403 and the adventure must remain. With your normal helper, deliberately delete it when finished:

```javascript
await dqQuestApi(`/api/adventures/${dqAdventure.id}/`, 'DELETE');
await dqQuestApi('/api/adventures/');
```

Expected HTTP 204 and no deleted UUID in the list; its retrieval URL now returns HTTP 404. Source counts remain 922 Places, 484 Parks and four DatasetSources. Existing saved adventures from other sessions are not affected.

The Leaflet map, numbered markers, radius/sequence overlays, builder form, stop cards and visible progress/completion are available at `/`. This console guide remains useful for testing the backend independently; see [FRONTEND_TESTING.md](FRONTEND_TESTING.md) to use the interface.

## Optional pedestrian route

`POST /api/adventures/{uuid}/walking-route/` with `{}` (or an empty body) requests
one `foot-walking` route through the saved origin and ordered stops. Use the same
session cookies and `X-CSRFToken` header as other guest mutations. Foreign owners
get 404; missing CSRF gets 403; GET is not supported. Client coordinates, profiles,
provider URLs and keys are not accepted. Source places moved since generation
require regeneration before routing.

The server uses `https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson`
with the optional server-side `ORS_API_KEY`, a 10-second network timeout, six
waypoints for a five-stop adventure, and a 50 m maximum snapping radius per point.
There is no optimization, automatic retry, provider switching or redirect following.
No original geometry, stop order, progress or model is changed.

Successful HTTP 200:

```json
{
  "status": "available",
  "route": {"type": "LineString", "coordinates": [[-6.26, 53.35], [-6.259, 53.35]]},
  "distance_m": 1608.1,
  "duration_s": 1157.8,
  "waypoints": [{"requested": [-6.26, 53.35], "snapped": [-6.26001, 53.35], "displacement_m": 0.67}],
  "warnings": [],
  "notice": "Estimated pedestrian route ...",
  "attribution": "openrouteservice.org | OpenStreetMap contributors"
}
```

This is an abbreviated shape example, not an actual complete provider response.
`route` is EPSG:4326 GeoJSON; waypoint pairs use longitude/latitude. Actual results
include one snapping entry for every requested waypoint. Distance/time describe
the snapped network route, exclude visits and do not verify off-network access
between the original attraction and its snapped point. Card distances remain
straight-line measurements.

Missing configuration, provider errors/limits, timeout, excessive snapping or an
invalid response return HTTP 200 with `status: "unavailable"` and a safe `detail`
message. The adventure remains usable with its original dashed sequence. Provider
error text, metadata and credentials are never forwarded. A best-effort per-session
30-second cooldown limits repeated requests; it is not a global quota or abuse
prevention system. All adventure responses retain private/no-store caching.

The browser stores only the current route result in page memory. Show/hide and
visited updates reuse it. Switching adventure or regenerating clears it. Reloading
requires an explicit new request; routes are not persisted to PostgreSQL.

The current URL follows the provider's
[HeiGIT migration](https://ask.openrouteservice.org/t/deprecating-api-openrouteservice-org-in-favour-of-api-heigit-org/7912).
See the [official response documentation](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/requests-and-return-types)
for geometry, summary and waypoint semantics.
