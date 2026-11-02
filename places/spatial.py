# Provide the three reusable PostGIS searches and their projected search-area buffer.
"""The three independently callable PostGIS operations used by the map APIs."""
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection


def nearby_places(queryset, origin, radius_m):
    # Projected geometries use metres. DWithin prefilters using the GiST index.
    return queryset.filter(point__dwithin=(origin, radius_m)).annotate(
        distance=Distance("point", origin)
    ).order_by("distance", "pk")


def contained_places(queryset, park):
    # coveredby includes boundary points, unlike strict within/contains.
    return queryset.filter(point__coveredby=park.boundary)


def buffered_search_area(origin, radius_m):
    # Construct the actual search polygon in PostGIS, not a browser-only circle.
    with connection.cursor() as cursor:
        cursor.execute("SELECT ST_AsEWKB(ST_Buffer(ST_GeomFromEWKB(%s), %s))", [origin.ewkb, radius_m])
        return GEOSGeometry(memoryview(cursor.fetchone()[0]))


def intersecting_parks(queryset, search_area):
    return queryset.filter(boundary__intersects=search_area)
