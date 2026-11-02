# Import qualified current Canvas artworks and report excluded or ambiguous source rows.
import json
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

from places.import_helpers import entry, finish, geojson_features, load_snapshot, projected_geometry, save_place, source_record, text_issue


class Command(BaseCommand):
    help = "Import current, named DCC Canvas artworks from the pinned 2025 snapshot."

    # Unexpected failures roll back this entire dataset; deliberate exclusions are reported.
    @transaction.atomic
    def handle(self, *args, **options):
        metadata, raw = load_snapshot("canvas")
        features = geojson_features(raw)
        source = source_record(metadata)
        report, candidates, seen = [], [], set()
        for row, feature in enumerate(features, 1):
            key = f"row:{row}"  # Stable only within the checksum-pinned snapshot.
            props = feature.get("properties") or {}
            geometry = feature.get("geometry")
            reason = None
            if not str(props.get("Artwork title:") or "").strip():
                reason = "missing_name"
            elif not geometry:
                reason = "missing_coordinates"
            elif props.get("Council:") != "Dublin City Council":
                reason = "outside_dcc_scope"
            elif props.get("Status:") != "1. Remain as is":
                reason = "historical_or_noncurrent_status"
            if reason:
                report.append(entry(row, key, "skipped", reason))
                continue
            issue = text_issue(props)
            if issue:
                report.append(entry(row, key, "quarantined", issue))
                continue
            fingerprint = json.dumps(feature, sort_keys=True)
            if fingerprint in seen:
                report.append(entry(row, key, "skipped", "exact_duplicate_feature"))
                continue
            seen.add(fingerprint)
            candidates.append((row, key, props, geometry))
        # Distinct current artworks sharing a point are ambiguous; do not choose one silently.
        by_point = defaultdict(list)
        for item in candidates:
            by_point[json.dumps(item[3], sort_keys=True)].append(item)
        for group in by_point.values():
            for row, key, props, geometry in group:
                if len(group) > 1:
                    report.append(entry(row, key, "quarantined", "conflicting_current_artworks_at_same_point"))
                    continue
                try:
                    point = projected_geometry(geometry, "Point")
                    created = save_place(source, key, name=props["Artwork title:"].strip(),
                        category="street_art", point=point, artist=props["Artist:"].strip(),
                        description=props["Location:"].strip(), profile_url=props["Website Profile:"].strip(), active=True)
                except ValidationError as error:
                    report.append(entry(row, key, "quarantined", "validation_failed", detail=str(error)))
                else:
                    report.append(entry(row, key, "imported", "eligible_current_artwork", created=created))
        finish(self, "canvas", metadata, sorted(report, key=lambda item: item["row"]))
