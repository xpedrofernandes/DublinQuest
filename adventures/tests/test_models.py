import uuid

from django.contrib.gis.geos import LineString, Point
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from adventures.models import Adventure, AdventureStop
from places.models import DatasetSource, Place


class AdventureModelTests(TestCase):
    def setUp(self):
        self.origin = Point(715000, 734000, srid=2157)
        self.adventure = Adventure.objects.create(
            owner_uuid=uuid.uuid4(), title="Synthetic test adventure", start=self.origin,
            categories=["heritage"], search_area=self.origin.buffer(2000),
            path=LineString((715000, 734000), (715100, 734000), srid=2157),
        )
        source = DatasetSource.objects.create(slug="fixture", title="Synthetic fixture", sha256="0" * 64)
        self.place = Place.objects.create(source=source, source_key="1", name="Test stop", category="heritage", point=Point(715100, 734000, srid=2157))

    def test_polygon_and_line_round_trip(self):
        self.adventure.refresh_from_db()
        self.assertEqual(self.adventure.path.srid, 2157)
        self.assertAlmostEqual(self.adventure.path.length, 100)
        self.assertTrue(self.adventure.search_area.covers(self.place.point))

    def test_category_validation_rejects_wrong_shape_duplicates_and_unknown_values(self):
        for categories in [[], "heritage", ["unknown"], ["heritage", "heritage"], [{}]]:
            self.adventure.categories = categories
            with self.subTest(categories=categories), self.assertRaises(ValidationError):
                self.adventure.full_clean()

    def test_database_rejects_out_of_range_radius(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Adventure.objects.filter(pk=self.adventure.pk).update(radius_m=1)

    def test_stop_uniqueness_and_deletion_rules(self):
        values = dict(adventure=self.adventure, place=self.place, position=1, distance_from_start_m=100, distance_from_previous_m=100)
        AdventureStop.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AdventureStop.objects.create(**values)
        with self.assertRaises(ProtectedError):
            self.place.delete()
        self.adventure.delete()
        self.assertFalse(AdventureStop.objects.exists())
        self.assertTrue(Place.objects.filter(pk=self.place.pk).exists())
