# Using and testing the DublinQuest interface

## Start the application

Complete the README setup, migrations and four imports first. Rebuild to include
updated templates and static files:

```bash
docker compose up -d --build --wait
```

Open **http://localhost:8000/**. No visitor login is required. JavaScript must be
enabled. Leaflet and Bootstrap assets are bundled locally; the basemap needs
internet access to OpenStreetMap. Do not test from a `file://` copy of the HTML.

## Generate your first adventure

1. Search for **Thomas Moore** under “Find a starting place”. Choose the imported
   statue near College Green/Trinity. The selected coordinates should be around
   `53.34517, -6.25892`. This is a statue location, not a verified campus entrance.
   Alternatively, click the map: the brown **S** marker identifies the new start.
2. Leave all four categories selected, choose **2 km** and **5 stops**. Give the
   adventure a name if desired, then select **Generate adventure**.
3. Expect five numbered map markers and five cards in the same order, a radius
   overlay, a connecting line and progress **0 of 5**. With the unchanged bundled
   data and the statue origin, the sequence is Normal People, Henry Grattan
   Statue, Stein Sculpture, Georges Quay and Hapenny Bridge. A nearby map click
   can produce a different sequence.
4. Read the straight-line notice. Distances are not walking distances; the radius
   limits each stop's distance from the origin, not the total sequence length.
   Georges Quay is a park representative point, not a verified entrance.
5. Select **Show on map** on a stop card. The corresponding marker should be
   centred and its popup should open. Pan, zoom using +/−, then use **Fit results**.
   The scale and OpenStreetMap attribution should remain visible.
6. Expand a card's **Data source & attribution**. Its original publisher and
   resource link should be present. Descriptions and names are source text;
   absent descriptions are explicitly identified rather than invented.

## Saving, progress and editing

- Adventures save automatically when generated. Check the saved-adventure card
  below the map/results. Reload the page, then select **Open adventure**: its
  stops and progress should reappear. The initial page does not automatically
  choose one of your saved adventures.
- Check **Visited** on the first stop. Expect **1 of 5 / 20%**. Reload and reopen
  to verify persistence. Uncheck it to return to zero.
- Mark all stops visited to see the completion message. This is a manual checklist,
  not GPS verification of a visit.
- **Rename** changes the saved title without resetting progress.
- Change the builder to three stops, then choose **Regenerate with form settings**.
  Confirm the reset. The same saved adventure now has three newly generated stops
  and zero visited progress. A deterministic algorithm can select the same places
  again when criteria are unchanged. Cancel leaves the adventure untouched.
- **Delete adventure** asks for confirmation, then removes that saved adventure
  and its progress. It does not delete imported places or parks.
- To check ownership, open a separate private-browser session or different browser
  profile. Its saved list should be empty. Ordinary tabs share the same session.
  Clearing cookies, session expiry or Django logout loses access to guest saves;
  there is no guest recovery or sharing mechanism.

## Demonstrate all three spatial operations

These controls work independently of adventure generation. Select a starting
point first for the radius searches. Results are a separate map layer and list;
**Clear layer** removes them without deleting the adventure.

| Control | What to check | Backend operation |
|---|---|---|
| **Find nearby places** | Places matching the selected categories within the chosen radius; changing radius/categories changes results | Indexed `dwithin` plus distance ordering |
| **Find parks overlapping radius** | Park boundary polygons intersecting the radius area; categories do not filter this query | Buffered search area and `intersects` |
| **Find places inside a park** | Search **Merrion**, choose **Inside Merrion Square**. With public art selected, expect nine places for the unchanged bundled data | Boundary-inclusive `coveredby` |

The park-containment control requires a non-park category. Other matching park
names may appear; choose Merrion Square specifically. Nearby/overlap/containment
requests follow every API page, avoiding the labs' first-page-only limitation.
Place/park name searches show up to 20 matches and ask you to refine broad searches.

## Errors, security and responsive behaviour

- Search for a nonexistent name: expect an empty-results message.
- Clear all categories and generate: expect a useful validation message, without
  changing the saved adventure. Restore at least one category afterwards.
- Choose a map point away from Dublin with no nearby data: generation should report
  insufficient eligible places rather than inventing stops. Where some places are
  available, the backend returns fewer stops with a visible warning.
- During requests, controls show a loading state and prevent duplicate submissions.
  A failed progress save restores the previous checkbox value.
- Reload after an expired CSRF token. Requests use the same-origin session cookies
  and the masked token obtained from `/api/session/`; no owner identifier or
  authentication token is stored in localStorage.
- Browser developer tools can simulate offline mode. Try **Refresh saved**: expect
  a connection error, then restore online mode. Previously displayed data stays
  visible. Missing map tiles produce a map-connectivity warning.
- Check widths around **1440 px**, **820 px** and **390 px**. The layout becomes one
  column on phones, controls remain readable, and the page should not scroll
  horizontally. Scroll-wheel zoom is deliberately disabled; +/− and touch zoom
  remain available. Real-device touch testing is still worthwhile.
- Use Tab/Shift+Tab and Enter/Space: the skip link, labelled form controls, search
  results, saved cards and visited controls must be usable. Place search is the
  keyboard alternative to choosing coordinates by map click. Feedback is announced
  through a live region. This is not a formal accessibility conformance audit.

## Automated checks

Run the Django/PostGIS suite using the restricted test-database setup documented
in DATABASE_SCHEMA.md:

```bash
docker compose run --rm -T web python manage.py test places adventures config --keepdb --verbosity 1
```

An additional browser smoke test is in `tests/browser/test_explore.py`. It uses
Playwright with the existing Google Chrome installation on macOS, in an isolated
guest context. Playwright is optional test tooling, not an application dependency;
no frontend build pipeline or browser automation package is installed in Docker.
For example, install it in a temporary host environment:

```bash
python3 -m venv /tmp/dq-browser-env
/tmp/dq-browser-env/bin/pip install playwright
/tmp/dq-browser-env/bin/python tests/browser/test_explore.py
```

Override `DQ_CHROME` for another Chrome executable location, or `DQ_TEST_URL` for
another local port. The test requires the unchanged imported data. It intercepts tile requests with
a tiny test image, so automated pan/zoom never fetches real OSM tiles. A loaded
image or HTTP 200 alone does not establish that the real basemap is working. It generates temporary adventures and deletes only those it created,
including on failure. Screenshots go to `/tmp/dublinquest-{desktop,tablet,mobile}.png`,
not the repository. It checks the user journey, all three spatial controls,
responsive overflow, errors, guest isolation and CSRF; it is not a comprehensive
cross-browser, screen-reader or performance test.

## Verify real OpenStreetMap tiles

Open the application normally in Chrome and confirm visible Dublin streets,
river and labels, not yellow/black Access blocked images. In Developer Tools:

1. Select Network, leave **Disable cache unchecked**, then filter for `tile.openstreetmap.org`.
2. Open a tile request. Its HTTPS URL must use
   `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
3. Request headers should include `Referer: http://localhost:8000/` when using the
   documented local address. The document response header must be
   `Referrer-Policy: strict-origin-when-cross-origin`. Cross-origin referrers
   disclose only the origin, not page paths or query strings.
4. Inspect the tile Preview: a successful status can still contain a block image.
   Verify actual map imagery and visible OpenStreetMap attribution. Normal browser
   caching is left intact; the API helper's `cache: no-store` applies only to API
   requests, not Leaflet's image requests.

The original Django default `same-origin` suppressed the tile referrer. A
regression assertion checks the new response header; browser interaction tests
use mock tiles and do not claim to verify live imagery. Do not add cache-busting
parameters, spoof headers, proxy requests to evade restrictions, prefetch tiles,
or run automated real-tile pan/zoom scans. See the official
[OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/).

## Optional walking route

This feature requires your own HeiGIT/openrouteservice key. Set `ORS_API_KEY` in
the ignored root `.env`, then run `docker compose up -d --wait web` so the container
receives it. Do not print resolved Compose configuration or share `.env`. With the
key blank, the complete original adventure experience remains available.

1. Generate the five-stop Thomas Moore/College Green example described above.
2. The stops and dashed fallback appear immediately, while **Calculating walking
   route…** and a spinner indicate the background request. Controls remain usable.
   The form discloses that coordinates are sent to HeiGIT through Django. On
   success, a solid blue route and estimated distance/time become primary; the
   dashed connection is hidden. **View straight-line sequence** switches views
   without another routing request; **View walking route** switches back.
3. Our live verification returned **1608.1 m / 1157.8 s (19.3 min)** and 99 route
   vertices. Maximum waypoint adjustment was 2.99 m; Georges Quay was 0.53 m.
   Results can change with the provider's data. The blue route followed mapped
   streets and south-bank quays rather than a direct diagonal across the Liffey.
4. Read the snapping/entrance disclaimer and any provider warning. The verified
   response warned that road-access-restriction extra information was unavailable.
   Markers stay at source coordinates; adjusted network positions are not verified
   entrances. Times exclude visits; this is not live turn-by-turn navigation.
5. Mark a stop visited. The selected route view should remain. Switch views, zoom
   and pan: none of these actions should make another walking-route request
   (check Network for `walking-route`). Open the same saved adventure: the cached
   result should display automatically without another request.
6. Regenerate or switch adventures: the previous overlay disappears, and routing
   loads automatically for the new selection. Switching back can reuse a cached
   result; regeneration invalidates the old one, even when the selected places
   are the same. A new request within 30 seconds can return the existing backend
   cooldown message and dashed fallback. Reloading discards page memory. Failed
   results are cached too; reload or regenerate later to retry.
7. Without a key, with an unreachable service or with an unroutable waypoint, expect
   an automatic fallback message and a fully usable dashed sequence, cards and progress.
   Automated tests cover these failures with mocks; do not deliberately spend live
   quota repeatedly testing provider failures.

All routing calls in `tests/browser/test_explore.py` are intercepted with mock
responses, just like OSM tiles. Backend routing tests mock the HTTP transport,
including invalid geometry, snapping, limits, timeouts, ownership and CSRF. The
single live verification is separate from regression tests. No routing SDK,
migration or external infrastructure is required.

Automatic-route regression checks hold a mocked response open to verify non-blocking
rendering, then test success, missing-key fallback, network errors, cached saved
loading, regeneration and ignored late responses. These checks consume no live
routing quota.
