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

The application is not runnable yet. Setup instructions and screenshots will be added as development progresses.
