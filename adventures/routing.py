# Request an optional pedestrian overlay while keeping stored quest geometry unchanged.
"""Optional ORS request; never changes the adventure or its stored geometry."""
import json
import math
import urllib.error
import urllib.request

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, Point

URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson"
MAX_SNAP_M = 50
NOTICE = "Estimated pedestrian route from openrouteservice/HeiGIT and OpenStreetMap. Walking time excludes visits. Access, opening hours and park entrances are not verified; markers remain at their original locations."


def unavailable(message):
    return {"status": "unavailable", "detail": message + " Showing the straight-line exploration sequence."}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirected host.
        return None


def walking_route(path):
    key = settings.ORS_API_KEY.strip()
    if not key:
        return unavailable("Walking routing is not configured.")
    # Transform a clone so the stored/projected sequence is never mutated.
    coordinates = list(path.transform(4326, clone=True).coords)
    payload = {"coordinates": coordinates, "instructions": False, "units": "m",
        "radiuses": [MAX_SNAP_M] * len(coordinates)}
    request = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": key, "Content-Type": "application/json", "Accept": "application/geo+json, application/json",
        "User-Agent": "DublinQuest/1.0 (university exploration application)",
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            # Read one byte beyond the limit to detect oversized provider responses.
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000 or key.encode() in raw:
            raise ValueError("Rejected response")
        data = json.loads(raw)
        if data.get("type") != "FeatureCollection" or len(data["features"]) != 1:
            raise ValueError("Expected one route")
        feature = data["features"][0]
        geometry = feature["geometry"]
        if geometry.get("type") != "LineString":
            raise ValueError("Expected LineString")
        points = geometry["coordinates"]
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("Expected route coordinates")
        for pair in points:
            if (not isinstance(pair, list) or len(pair) != 2
                    or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in pair)
                    or not -180 <= pair[0] <= 180 or not -90 <= pair[1] <= 90):
                raise ValueError("Invalid coordinates")
        clean_geometry = {"type": "LineString", "coordinates": points}
        line = GEOSGeometry(json.dumps(clean_geometry), srid=4326)
        if line.empty or not line.valid or line.length == 0:
            raise ValueError("Invalid route")
        properties = feature["properties"]
        distance, duration = properties["summary"]["distance"], properties["summary"]["duration"]
        for value in (distance, duration):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid summary")
        # Require an ordered vertex index for the origin and every requested stop.
        indices = properties["way_points"]
        if (not isinstance(indices, list) or len(indices) != len(coordinates)
                or any(type(i) is not int or not 0 <= i < len(points) for i in indices)
                or indices != sorted(indices) or indices[0] != 0 or indices[-1] != len(points) - 1):
            raise ValueError("Invalid waypoint indices")
        waypoints = []
        for original, index in zip(coordinates, indices):
            snapped = points[index]
            source = Point(*original, srid=4326).transform(2157, clone=True)
            target = Point(*snapped, srid=4326).transform(2157, clone=True)
            # Measure snapping in projected metres; keep attraction markers unchanged.
            displacement = source.distance(target)
            if not math.isfinite(displacement) or displacement > MAX_SNAP_M + 1:
                raise ValueError("Snapping exceeds requested tolerance")
            waypoints.append({"requested": original, "snapped": snapped, "displacement_m": round(displacement, 2)})
        # Whitelist output; never relay provider metadata, headers or error text.
        warnings = ["The provider reported a routing warning; road access information may be incomplete."] if properties.get("warnings") else []
        return {"status": "available", "route": clean_geometry, "distance_m": distance, "duration_s": duration,
            "way_points": indices, "waypoints": waypoints, "warnings": warnings, "notice": NOTICE,
            "attribution": "openrouteservice.org | OpenStreetMap contributors"}
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 429):
            return unavailable("Walking routing is unavailable because of provider authorization or usage limits.")
        return unavailable("The provider could not calculate a walking route through all stops.")
    except Exception:
        # External failures must not expose credentials or break the saved adventure.
        # Deliberately do not log the request, raw response or exception details.
        return unavailable("Walking routing could not be completed; the service may be unavailable or returned an invalid response.")
