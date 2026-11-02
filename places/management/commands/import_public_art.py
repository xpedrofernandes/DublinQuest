# Load the public-art CSV using an explicitly declared geographic coordinate interpretation.
import csv
import io

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from places.import_helpers import entry, finish, load_snapshot, projected_geometry, save_place, source_record, text_issue


class Command(BaseCommand):
    help = "Import DCC public artworks; explicitly declare the CSV coordinate interpretation."

    def add_arguments(self, parser):
        parser.add_argument("--source-srid", type=int, choices=[4326], required=True,
            help="CSV has no explicit datum; 4326 declares the documented WGS84 interpretation.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get("source_srid") != 4326:
            raise CommandError("Explicit --source-srid 4326 is required for the CSV.")
        metadata, raw = load_snapshot("public_art")
        source = source_record(metadata)
        rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        report, seen = [], set()
        for row, props in enumerate(rows, 1):
            key = f"row:{row}"
            if not props["Latitude"].strip() or not props["Longitude"].strip():
                report.append(entry(row, key, "skipped", "missing_coordinates"))
                continue
            # Match full rows: repeated artwork names alone do not establish duplicates.
            fingerprint = tuple(sorted(props.items()))
            if fingerprint in seen:
                report.append(entry(row, key, "skipped", "exact_duplicate_record"))
                continue
            seen.add(fingerprint)
            issue = text_issue(props)
            if issue:
                report.append(entry(row, key, "quarantined", issue))
                continue
            try:
                geometry = {"type": "Point", "coordinates": [float(props["Longitude"]), float(props["Latitude"])]}
                point = projected_geometry(geometry, "Point")
                created = save_place(source, key, name=props["CultureName "].strip(),
                    description=props["Description"].strip(), category="public_art", point=point,
                    profile_url=props["Website"].strip(), active=True)
            except (ValueError, ValidationError) as error:
                report.append(entry(row, key, "quarantined", "validation_failed", detail=str(error)))
            else:
                report.append(entry(row, key, "imported", "valid_public_artwork", created=created))
        finish(self, "public_art", metadata, report,
            warnings=["CSV datum is not explicit in the source. --source-srid 4326 declares the WGS84 interpretation; it is not publisher verification."])
