"""Small deterministic selection algorithm; no walking or routing engine."""
from django.contrib.gis.geos import LineString
from rest_framework.exceptions import ValidationError

from places.models import Place
from places.spatial import buffered_search_area, nearby_places

SEQUENCE_NOTICE = "Straight-line suggested sequence, not pedestrian routing or walking directions. Park points are representative locations, not verified entrances."


def generate_adventure(start, categories, radius_m, stop_count):
    queryset = Place.objects.filter(active=True, category__in=categories).exclude(park__active=False)
    candidates = []
    seen_points = set()
    for place in nearby_places(queryset, start, radius_m):
        # Millimetre precision prevents coincident stops and round-trip noise.
        key = (round(place.point.x, 3), round(place.point.y, 3))
        if place.point.distance(start) <= 0.001 or key in seen_points:
            continue
        seen_points.add(key)
        candidates.append(place)
    if not candidates:
        raise ValidationError({"detail": "No eligible locations were found. Try other categories, a different start or a larger radius."})

    # Reserve the nearest location from each available category, prioritizing
    # categories whose closest location is nearer when there are few slots.
    nearest_by_category = {}
    for place in candidates:
        nearest_by_category.setdefault(place.category, place)
    chosen = sorted(nearest_by_category.values(), key=lambda p: (p.distance.m, p.pk))[:stop_count]
    chosen_ids = {place.pk for place in chosen}
    for place in candidates:
        if len(chosen) == stop_count:
            break
        if place.pk not in chosen_ids:
            chosen.append(place)
            chosen_ids.add(place.pk)

    # Greedy nearest-next ordering over at most ten selected locations.
    ordered = []
    current = start
    while chosen:
        place = min(chosen, key=lambda p: (current.distance(p.point), p.pk))
        ordered.append({"place": place, "distance_from_start_m": start.distance(place.point),
            "distance_from_previous_m": current.distance(place.point)})
        chosen.remove(place)
        current = place.point
    coordinates = [start.coords] + [stop["place"].point.coords for stop in ordered]
    path = LineString(coordinates, srid=2157)
    return {"stops": ordered, "path": path, "search_area": buffered_search_area(start, radius_m)}
