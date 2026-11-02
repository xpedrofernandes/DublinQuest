import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from places.import_helpers import entry, finish, geojson_features, load_snapshot, projected_geometry, save_place, source_record, text_issue


class Command(BaseCommand):
    help = "Import qualified heritage points, quarantining damaged text and the unverified Trinity point."

    @transaction.atomic
    def handle(self, *args, **options):
        metadata, raw = load_snapshot("heritage")
        source = source_record(metadata)
        report, seen = [], set()
        for row, feature in enumerate(geojson_features(raw), 1):
            key = f"row:{row}"
            props = feature["properties"]
            if not feature.get("geometry"):
                report.append(entry(row, key, "skipped", "missing_coordinates"))
                continue
            issue = text_issue(props)
            if issue or props["Title"] == "Trinity College Dublin":
                report.append(entry(row, key, "quarantined", issue or "trinity_position_requires_verification"))
                continue
            fingerprint = json.dumps(feature, sort_keys=True)
            if fingerprint in seen:
                report.append(entry(row, key, "skipped", "exact_duplicate_feature"))
                continue
            seen.add(fingerprint)
            try:
                point = projected_geometry(feature["geometry"], "Point")
                created = save_place(source, key, name=props["Title"].strip(),
                    description=props["Description"].strip(), category="heritage", point=point, active=True)
            except ValidationError as error:
                report.append(entry(row, key, "quarantined", "validation_failed", detail=str(error)))
            else:
                report.append(entry(row, key, "imported", "valid_heritage_point", created=created))
        finish(self, "heritage", metadata, report)
