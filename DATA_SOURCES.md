# DublinQuest data qualification

Inspected 2 November 2026. This records the downloaded source snapshots and import decisions to review before implementing models or loaders. No records have been imported or repaired.

## Sources and reproducibility

The manifest pins the four original Smart Dublin resources selected for DublinQuest. Exact resource IDs and download URLs are recorded in `data/sources.json`; no alternate resource or newer dataset was substituted.

| Local file in `data/raw/` | Source/version | Records | Geometry | Bytes |
|---|---|---:|---|---:|
| `canvas.geojson` | [Dublin Canvas, Spring/May 2025](https://data.smartdublin.ie/dataset/6342875e-0ab4-444b-bd32-f22a234c1452/resource/58066cda-d1e3-4466-bf3e-c2a2924e0abf) | 912 | 874 Point, 38 missing | 450,363 |
| `public_art.csv` | [DCC permanent public art, July 2021 review](https://data.smartdublin.ie/dataset/278d861a-3e4a-4163-a8ef-1592bfc564b3/resource/c019d8bf-03a6-4a1e-a47e-1ece57ea07e7) | 82 | 82 coordinate pairs → Point | 30,938 |
| `heritage.geojson` | [Heritage/monuments/government buildings, January 2024 resource](https://data.smartdublin.ie/dataset/a9f33a10-62a2-4b29-b09c-a93933b6bbba/resource/447cec2f-f039-4639-8ae8-76068182218a) | 45 | Point | 20,865 |
| `parks.geojson` | [DCC Parks Strategy 2016 mapping](https://data.smartdublin.ie/dataset/6fde9a72-2f29-4e5a-b2aa-d02b2a2cdc2d/resource/42fec1fb-5d7e-4946-b996-982037782b3d) | 566 | MultiPolygon | 2,767,840 |

`data/sources.json` contains exact download/resource URLs, resource modification timestamps, SHA-256 checksums, publisher and catalogue licence fields. The catalogue's version fields are blank; the versions above describe the source filenames/notes, not invented release numbers. Recent metadata updates do not make the underlying data current. In particular the parks publisher explicitly says the 2016 mapping has not been updated.

The four original data snapshots are bundled in `data/raw/` as third-party Dublin City Council open data, separate from the original DublinQuest application code. Their source licences apply independently of any application-code licence. The snapshots are unchanged, including known source defects, and included in Docker builds for future import commands. Full CKAN metadata dumps and any other files in that folder remain ignored and excluded from Docker builds. Downloaded files were parsed as GeoJSON FeatureCollections or CSV with the required headers; none was an HTML error page. Canvas is structurally readable but is not valid UTF-8 GeoJSON as supplied.

A fresh clone includes all four source files: no external dataset download is required. After creating the Phase 0 Docker environment, the existing script can verify their checksums locally and the inspection can be repeated:

```bash
python3 scripts/download_datasets.py
docker compose run --rm --no-deps \
  -v "$PWD/data/raw:/datasets:ro" \
  -v "$PWD/scripts/qualify_datasets.py:/qualification.py:ro" \
  web python /qualification.py /datasets > data/qualification.json
```

The verification script uses Python's standard library. With the bundled files present, it makes no network requests and does not need curl. If a file is missing, it can recover the exact snapshot using system `curl` with TLS verification. It checks hashes before writing and fails if a resource changes; existing files are verified rather than overwritten. Git attributes disable text/line-ending conversion for these four files to preserve the recorded bytes on macOS and Windows. Future dataset-specific import commands will read these local snapshots; those commands do not exist yet.

The inspection script uses GeoDjango's GEOS/GDAL tools already in the web image. It reads mounted files only, transforms copies to EPSG:2157 for metric checks, and writes JSON to stdout. It does not access Django models, load a database or implement an ETL framework. Row references in the report are one-based data rows/features, excluding the CSV header. `data/qualification.json` is generated and ignored.

## CRS and geometry checks

All three GeoJSON files explicitly declare `urn:ogc:def:crs:OGC:1.3:CRS84`: WGS84 longitude, latitude. Interpret those axes correctly when transforming to the approved EPSG:2157 storage CRS. Leaflet will receive latitude, longitude arrays, while GeoJSON remains longitude, latitude.

The public-art CSV has named Latitude/Longitude columns and Dublin-range numeric values. Its catalogue describes latitude/longitude but does not explicitly establish the datum in the inspected metadata. EPSG:4326 is the proposed interpretation, pending corroboration or source confirmation; it is not an embedded verified CSV CRS.

Every nonmissing geometry parsed, was nonempty and had finite geographic coordinates within valid longitude/latitude ranges. This validates structure, not whether a marker is accurately placed or a place is publicly accessible. All point geometries are GEOS-valid. Eight park MultiPolygons are invalid due to self-intersections; see below. No source provides LineStrings: those will be generated from adventure stop sequences in a later phase.

## Dublin Canvas

Fields: `Council:`, `GPS:`, `Artist:`, `Artwork title:`, `Location:`, `Area:`, `Year:`, `Status:`, `Website Profile:`, `field_12`. The punctuation is part of the source column names. There is no general description field; use the supplied artist/location information rather than inventing descriptions.

- 38 features lack geometry, including 14 blank trailing records. Fourteen rows have missing values in every main property; `field_12` is empty throughout.
- There are 13 malformed UTF-8 bytes across rows 69, 129, 242, 419, 574, 724, 821, 825 and 874. Row 78 additionally contains an existing Unicode replacement character. The audit uses `surrogateescape` only to inspect structure; this is not an approved decoding or text-repair strategy for import.
- Eight exact duplicate feature groups exist: seven pairs and the 14 blank rows. There are 170 repeated-coordinate groups and 25 repeated normalized-title groups. Many coordinates refer to successive artworks at the same traffic box; do not treat all historic versions as separate current stops.
- Council counts: DCC 645; Dún Laoghaire-Rathdown 89; Fingal 55; South Dublin 109; blank 14.
- Status counts: `1. Remain as is` 526; `2. Painted Over` 256; `3. Repaint 2025` 91; `5. Removed` 7; `6. Reverted to grey` 18; blank 14.
- `Year:` mixes single years, year ranges and whitespace; preserve as source text rather than forcing an integer.
- Profile URLs repeat, including a shared general link; they are not reliable primary keys. Neither artwork titles nor coordinates uniquely identify all source records.

Recommended initial eligibility: named DCC records with valid geometry and `1. Remain as is`; exclude painted-over/removed/grey/repaint-pending records from current attraction searches. This leaves 327 candidate rows at 322 unique points before text review and duplicate resolution. The catalogue is a May 2025 snapshot, so even that status does not verify physical presence in November 2026. Quarantine malformed text for explicit review; never silently replace all errors or reinterpret the entire mixed file as Latin-1. Keep the original bytes unchanged.

The catalogue description mentions 898 boxes, matching nonblank property rows, rather than the 912 raw features or 874 usable geometries. These are different counts.

## Public artworks

Relevant fields: `CultureName ` (trailing space), `Description`, `Latitude`, `Longitude`, `Website`, neighbourhood, public category, DCC area and contact fields. All 82 rows have a name, description and numeric coordinate pair; no null/blank cells were found under the audit's null/whitespace definition. No exact row or coordinate duplicates were found.

There are two repeated-name pairs: Henry Grattan Statue (rows 4 and 18) and Luke Kelly Statue (74 and 75). Their descriptions and coordinates differ: these are distinct listed artworks, not records to delete solely because names match. `Website` links are unique in this snapshot but are shortened map links, not guaranteed permanent identifiers or artwork-profile pages.

Contact postal fields describe the Dublin City Arts Office in the sample inspected; do not display them as each sculpture's physical address. Keep names, descriptions and coordinates as the main location content. No malformed UTF-8 or obvious mojibake was detected. The July 2021 review date means current presence/access still needs a demonstration spot-check.

## Heritage, monuments and government buildings

Fields: `Title`, `Description`, `Address1`, `Address2`, `NaceCode`, `Region`, `DccAreaNew`, `CensusSmallArea`, `ElectoralDivision`. All 45 features have a title, description and geometry; 36 have blank `Address2`. No exact record, coordinate or normalized-title duplicates were found.

The UTF-8 file already contains mojibake in titles at rows 12 and 41 (Glasnevin/St. Mobhi's and Áras an Uachtaráin). Preserve the source and make any reviewed text corrections explicit later. Valid UTF-8 alone does not establish clean text.

The supplied Trinity College Dublin point is `[-6.240971039, 53.34242192]`, with address `College Green`. It remains a positional concern identified in earlier research, not a verified entrance or corrected point. Spot-check it against an authoritative site map before offering it as the default start; an arbitrary map click remains an approved fallback. No corrected coordinate is asserted here. This dataset also includes government buildings and cemeteries, so the category should not promise that every record is an ancient monument or freely accessible visitor attraction.

## Parks and open spaces

All 566 features are MultiPolygons. `PRIMARYINDEX` is populated and unique; use it as the source identifier. `Park_ID` is missing for 11 rows and has six repeated-value groups, so it is unsuitable as a unique key. Seven park names are missing; 13 normalized-name groups repeat, but no exact feature or geometry duplicates were found. Separate parcels may legitimately share a name; do not merge them automatically.

Fields include name, location, class, typology, source area and amenity indicators. `Location` is missing for 461 rows; `Management` and `Model_Car_Racing` are missing throughout. Other amenity fields are very sparse. Missing is unknown, not proof that an amenity is absent. The `Multipolygon` property is a sparse attribute, not the authoritative geometry field. Class values mix `04` and `4`, plus OPW/DDDA labels; use `Typology` for straightforward filtering.

Typologies: 406 amenity public open spaces, 53 institutional land, 33 community parks grade 2, 19 graveyards, 18 community parks grade 1, 17 greenways, 10 OPW parks, 8 flagship parks and 2 Georgian squares. Not all 566 records are suitable adventure stops.

Invalid boundary rows:

| Row | Source name | GEOS issue |
|---:|---|---|
| 39 | Amenity Open Space | Ring self-intersection |
| 169 | Leinster Sports Complex | Self-intersection |
| 170 | YMCA Recreational Grounds | Ring self-intersection |
| 222 | Drimnagh Castle School Grounds | Ring self-intersection |
| 295 | Missing | Self-intersection |
| 333 | Le Fanu Park | Ring self-intersection |
| 468 | Edenmore Green | Ring self-intersection |
| 540 | Church of Ireland Openspace 3 | Self-intersection |

Initial recommendation: quarantine these eight rather than silently repairing boundaries. If retaining a particular park later matters, review a GEOS/PostGIS make-valid result explicitly, including geometry type and area changes. This is not required to establish sufficient coverage now.

For park attraction candidates, require a name and valid boundary and initially exclude institutional land and graveyards. This gives 484 candidates, without claiming verified public access. Derive a point-on-surface only when importing later, label it as a representative point rather than an entrance, and calculate areas from transformed geometry rather than trusting the source area fields as current measurements.

## Spatial functionality and coverage evidence

The inspection uses illustrative Dublin-centre coordinates `(-6.26, 53.35)`, not a claimed landmark entrance. At 2 km:

- 92 Canvas rows satisfy the named-DCC/remain-status selection before text/deduplication review.
- 63 public artworks and 26 heritage features have source points within the radius.
- 55 of the 484 proposed park candidates intersect the buffered search area; 51 have a representative point within the radius. Intersection and representative-point distance are intentionally different tests.

This is enough candidate density for a five-stop central adventure without inventing attractions. It is not a guarantee for every category, radius or start; sparse results must remain visible rather than widening the radius silently. Exact post-import counts will depend on the reviewed exclusions.

Containment has real positive examples: Merrion Square boundary (row 373) covers nine source public-art points; St. Patricks Park (42) covers two; Pearse Square (10) covers one. These were tested with GEOS `covers` on valid projected geometry, not yet through database queries or frontend interactions. They provide practical fixtures for later PostGIS containment demonstrations.

There are no exact normalized-name matches between the three point datasets. Five cross-source pairs lie within 20 metres, but their names indicate different objects (for example a Canvas box near Thomas Moore Statue). Proximity alone is not evidence that records should be merged. Review any future park/heritage representative-place overlap separately.

## Licensing and attribution

All four downloaded CKAN package responses identify Dublin City Council as the publishing organization and list `cc-by`, “Creative Commons Attribution”, linking to `http://www.opendefinition.org/licenses/cc-by`. This is a generic licence-family URL, not an explicit version per dataset. [Open Definition's page](https://opendefinition.org/licenses/cc-by/) links to CC BY 4.0 and earlier versions; do not silently claim that the metadata establishes a specific version. Confirm the version with the publisher if a version-specific notice is needed.

Keep the supplied attribution, dataset title, publisher, resource link and licence link with each source. For Canvas also retain artist credits; for public art/heritage acknowledge the Dublin City Cultural Audit / Dublin City Council Culture Company context. Record modifications such as filtering, coordinate transformation, representative points and reviewed text corrections. The [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) explains credit, licence linking and identification of changes; retain the actual supplied licence notice as well.

The bundled raw snapshots are unmodified and have not yet been filtered or transformed. Attribution for these snapshots: “Dublin City Council open data via Smart Dublin: Dublin Canvas Public Art (2025), Public Artworks DCC (2021), Heritage Sites, Historic Monuments and Government Buildings (2024), and Parks and Open Spaces DCC (2016). Creative Commons Attribution.” The table above links each source; the publisher licence notice is retained above and in `data/sources.json`. Artist credits remain in the Canvas data. No photographs or external images are included.

Proposed attribution text for the future processed application data: “Contains Dublin City Council open data from Smart Dublin: Dublin Canvas Public Art (2025), Public Artworks DCC (2021), Heritage Sites, Historic Monuments and Government Buildings (2024), and Parks and Open Spaces DCC (2016), published under Creative Commons Attribution. Data filtered and transformed for DublinQuest.” Link each title and the supplied licence notice in the eventual application. Do not imply endorsement. Dataset availability does not establish rights to download/rehost linked artwork photographs; no images were downloaded.

## Comparison and remaining checks

Counts, bytes, geometry types, Canvas null geometry and the Trinity positional concern match the earlier research. Old snapshot checksums were not retained, so byte-for-byte identity with Windows originals cannot be proved. Newly established findings include eight invalid park boundaries, detailed duplicate groups, status-qualified Canvas coverage and heritage mojibake. No original files were changed.

Before import: review malformed Canvas text/overlapping current records, inspect representative attractions on a map, corroborate the CSV datum, and retain licence-version uncertainty explicitly. No geographic-accuracy audit of every attraction, access survey, source area reconciliation, live artwork-profile validation or image-rights review has been performed. Simple dataset-specific management commands will implement reviewed decisions later; this phase adds neither models nor database import commands.
