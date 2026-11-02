from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from places.import_helpers import entry, finish, geojson_features, load_snapshot, projected_geometry, save_place, source_record
from places.models import Park


class Command(BaseCommand):
    help = "Import named valid parks and explicitly synchronize their representative places."

    @transaction.atomic
    def handle(self, *args, **options):
        metadata, raw = load_snapshot("parks")
        source = source_record(metadata)
        report, seen = [], set()
        for row, feature in enumerate(geojson_features(raw), 1):
            props = feature["properties"]
            key = str(props["PRIMARYINDEX"])
            # Check validity first so every invalid boundary has a quarantine record.
            try:
                boundary = projected_geometry(feature.get("geometry"), "MultiPolygon")
            except ValidationError as error:
                report.append(entry(row, key, "quarantined", "invalid_boundary", detail=str(error)))
                continue
            if not str(props.get("Name") or "").strip():
                report.append(entry(row, key, "skipped", "missing_name"))
                continue
            if props["Typology"] in ("Institutional Land", "Graveyards"):
                report.append(entry(row, key, "skipped", "excluded_park_typology"))
                continue
            if key in seen:
                report.append(entry(row, key, "quarantined", "duplicate_primaryindex"))
                continue
            seen.add(key)
            try:
                # A failed representative-place validation must not leave half a pair.
                with transaction.atomic():
                    park = Park.objects.filter(source=source, source_key=key).first()
                    created = park is None
                    if created:
                        park = Park(source=source, source_key=key)
                    park.name = props["Name"].strip()
                    park.typology = props["Typology"]
                    park.boundary = boundary
                    park.active = True
                    park.full_clean()
                    park.save()
                    place_created = save_place(source, key, name=park.name, category="park",
                        description="Representative point within the source park boundary; not a verified entrance.",
                        park=park, point=boundary.point_on_surface, active=True)
            except ValidationError as error:
                report.append(entry(row, key, "quarantined", "validation_failed", detail=str(error)))
            else:
                report.append(entry(row, key, "imported", "valid_park_and_representative_place", created=created, place_created=place_created))
        finish(self, "parks", metadata, report)
