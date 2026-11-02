# Load bundled snapshots into the test database to check repeatability and quarantine decisions.
import io
import json
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase

from places.import_helpers import save_place
from places.models import DatasetSource, Park, Place


class DatasetImportTests(TestCase):
    def run_import(self, name):
        output = io.StringIO()
        options = {"source_srid": 4326} if name == "public_art" else {}
        call_command(f"import_{name}", stdout=output, **options)
        return json.loads(output.getvalue())

    def test_bundled_imports_are_complete_repeatable_and_spatially_correct(self):
        expected = {"canvas": (912, 314, 586, 12), "public_art": (82, 82, 0, 0),
                    "heritage": (45, 42, 0, 3), "parks": (566, 484, 74, 8)}
        first_reports = {}
        for name, counts in expected.items():
            report = self.run_import(name)
            first_reports[name] = report
            self.assertEqual(tuple(report[k] for k in ("total", "imported", "skipped", "quarantined")), counts)
            self.assertEqual(report["created"], counts[1])
            self.assertEqual({row["row"] for row in report["records"]}, set(range(1, counts[0] + 1)))
            self.assertTrue(all(row["reason"] for row in report["records"]))
        # A second full run must preserve primary keys, outcomes and record counts.
        before = list(Place.objects.order_by("pk").values_list("pk", "source_id", "source_key"))
        park_ids = list(Park.objects.order_by("pk").values_list("pk", flat=True))
        for name in expected:
            report = self.run_import(name)
            self.assertEqual(report["created"], 0)
            self.assertEqual(report["updated"], expected[name][1])
            self.assertEqual(
                [(row["row"], row["outcome"], row["reason"]) for row in report["records"]],
                [(row["row"], row["outcome"], row["reason"]) for row in first_reports[name]["records"]],
            )
        self.assertEqual(before, list(Place.objects.order_by("pk").values_list("pk", "source_id", "source_key")))
        self.assertEqual(park_ids, list(Park.objects.order_by("pk").values_list("pk", flat=True)))
        self.assertEqual((DatasetSource.objects.count(), Place.objects.count(), Park.objects.count()), (4, 922, 484))
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM places_place WHERE ST_SRID(point) <> 2157 OR NOT ST_IsValid(point)")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("SELECT count(*) FROM places_park WHERE ST_SRID(boundary) <> 2157 OR NOT ST_IsValid(boundary)")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("SELECT count(*) FROM places_place p JOIN places_park k ON p.park_id=k.id WHERE NOT ST_Covers(k.boundary, p.point)")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("""SELECT ST_Distance(point, ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),2157))
                FROM places_place p JOIN places_datasetsource s ON p.source_id=s.id
                WHERE s.slug='public_art' AND p.source_key='row:1'""", [-6.258924007, 53.34516502])
            self.assertLess(cursor.fetchone()[0], 0.01)
        self.assertEqual(Place.objects.filter(name="Luke Kelly Statue").count(), 2)
        park = Park.objects.first()
        Place.objects.filter(park=park).update(point=Place.objects.filter(category="public_art").first().point)
        self.run_import("parks")
        park.place.refresh_from_db()
        self.assertTrue(park.boundary.point_on_surface.equals_exact(park.place.point, 0.001))

    def test_changed_snapshot_is_rejected_before_database_writes(self):
        with patch.object(Path, "read_bytes", return_value=b"changed source"), self.assertRaises(CommandError):
            self.run_import("canvas")
        self.assertEqual(DatasetSource.objects.count(), 0)
        self.assertEqual(Place.objects.count(), 0)

    def test_csv_requires_explicit_coordinate_interpretation(self):
        with self.assertRaises(CommandError):
            call_command("import_public_art", stdout=io.StringIO())
        self.assertFalse(DatasetSource.objects.exists())

    def test_unexpected_failure_rolls_back_entire_dataset(self):
        calls = 0

        def fail_on_second_place(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated unexpected write failure")
            return save_place(*args, **kwargs)

        with patch("places.management.commands.import_public_art.save_place", side_effect=fail_on_second_place):
            with self.assertRaises(RuntimeError):
                self.run_import("public_art")
        self.assertFalse(DatasetSource.objects.exists())
        self.assertFalse(Place.objects.exists())
