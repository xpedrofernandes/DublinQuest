# Check source uniqueness, geometry validation, coordinate round trips and GiST indexes.
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from places.models import DatasetSource, Park, Place


class SpatialModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = DatasetSource.objects.create(
            slug="fixture", title="Synthetic test fixture", publisher="Tests",
            resource_url="https://example.com/data", licence_name="Test only",
            licence_url="https://example.com/licence", attribution="Synthetic geometry",
            snapshot_filename="fixture.json", sha256="0" * 64,
        )

    def test_point_round_trip_uses_projected_metres(self):
        point = Point(-6.26, 53.35, srid=4326)
        point.transform(2157)
        place = Place.objects.create(source=self.source, source_key="1", name="Test point", category="heritage", point=point)
        place.refresh_from_db()
        self.assertEqual(place.point.srid, 2157)
        place.point.transform(4326)
        self.assertAlmostEqual(place.point.x, -6.26, places=6)
        self.assertAlmostEqual(place.point.y, 53.35, places=6)

    def test_duplicate_source_record_is_rejected_by_database(self):
        values = dict(source=self.source, source_key="1", name="Test", category="heritage", point=Point(715000, 734000, srid=2157))
        Place.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Place.objects.create(**values)

    def test_invalid_boundary_is_rejected_by_validation(self):
        bow_tie = Polygon(((0, 0), (2, 2), (0, 2), (2, 0), (0, 0)), srid=2157)
        park = Park(source=self.source, source_key="invalid", name="Invalid", boundary=MultiPolygon(bow_tie, srid=2157))
        with self.assertRaises(ValidationError):
            park.full_clean()

    def test_geometry_columns_have_gist_indexes(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT tablename, indexdef FROM pg_indexes WHERE schemaname='public' AND indexdef ILIKE '%USING gist%'")
            indexes = cursor.fetchall()
        for table, field in [("places_place", "point"), ("places_park", "boundary"), ("adventures_adventure", "start"), ("adventures_adventure", "search_area"), ("adventures_adventure", "path")]:
            self.assertTrue(any(t == table and f"({field})" in sql for t, sql in indexes), (table, field))
