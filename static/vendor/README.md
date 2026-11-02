# Frontend libraries

These are third-party libraries, separate from the original DublinQuest code.
They are bundled so the interface does not depend on a JavaScript/CSS CDN.

- Leaflet 1.9.4: `https://unpkg.com/leaflet@1.9.4/dist/leaflet.js` and
  `https://unpkg.com/leaflet@1.9.4/dist/leaflet.css`. BSD-2-Clause licence in
  `leaflet/LICENSE`, retrieved from `https://unpkg.com/leaflet@1.9.4/LICENSE`.
- Bootstrap 5.3.8 CSS: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css`.
  MIT licence in `bootstrap/LICENSE`, retrieved from
  `https://raw.githubusercontent.com/twbs/bootstrap/v5.3.8/LICENSE`.

Retrieved 2 November 2026. Source maps and the three images referenced by
Leaflet CSS are included from the same versioned distribution paths so Django
collectstatic can resolve all references. The app uses CSS/HTML markers. These
small library icons are not dataset photographs. Bootstrap JavaScript is not
needed. OpenStreetMap tiles still need internet access.
