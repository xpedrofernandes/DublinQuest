# Share snapshot verification, geometry validation and import reporting across datasets.
"""Small shared checks for the four dataset-specific management commands."""
import hashlib
import json
import math
from collections import Counter

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError

from .models import DatasetSource, Place


def load_snapshot(slug):
    # Import rules apply to these exact qualified bytes, not an updated download.
    manifest = json.loads((settings.BASE_DIR / "data/sources.json").read_text())
    source = next(item for item in manifest if item["name"] == slug)
    raw = (settings.BASE_DIR / "data/raw" / source["filename"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise CommandError("Source checksum mismatch; qualify changed data before importing.")
    return source, raw


def source_record(metadata):
    # Reuse provenance on repeat imports instead of creating another source row.
    source, _ = DatasetSource.objects.update_or_create(
        slug=metadata["name"], defaults={
            "title": metadata["title"], "publisher": metadata["organization"],
            "resource_url": metadata["resource_page"],
            "licence_name": metadata["license_title"], "licence_url": metadata["license_url"],
            "attribution": f"{metadata['organization']} via Smart Dublin: {metadata['title']}. {metadata['license_title']}. Original snapshot; filtering and coordinate transformation for DublinQuest.",
            "snapshot_filename": metadata["filename"], "sha256": metadata["sha256"],
        },
    )
    return source


def geojson_features(raw):
    # Preserve bad bytes for row-level quarantine, never silently replace text.
    data = json.loads(raw.decode("utf-8-sig", errors="surrogateescape"))
    if data.get("type") != "FeatureCollection" or data.get("crs", {}).get("properties", {}).get("name") != "urn:ogc:def:crs:OGC:1.3:CRS84":
        raise CommandError("Expected the qualified CRS84 FeatureCollection.")
    return data["features"]


def text_issue(properties):
    """Flag undecodable or suspicious text for review rather than repairing it."""
    for value in properties.values():
        if not isinstance(value, str):
            continue
        if any(0xDC80 <= ord(c) <= 0xDCFF for c in value):
            return "malformed_utf8"
        if any(c in value for c in ("\ufffd", "Ã", "Â")):
            return "damaged_text_requires_review"
    return None


def projected_geometry(geometry, expected_type):
    """Validate source longitude/latitude geometry and project it into metres."""
    if not geometry or geometry.get("type") != expected_type:
        raise ValidationError("Missing or unexpected geometry type.")
    geom = GEOSGeometry(json.dumps(geometry), srid=4326)
    if geom.empty or not geom.valid:
        raise ValidationError(f"Empty or invalid geometry: {geom.valid_reason}; no automatic repair.")
    west, south, east, north = geom.extent
    if not all(math.isfinite(x) for x in geom.extent) or not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValidationError("Coordinates outside longitude/latitude bounds.")
    geom.transform(2157)
    if not geom.valid:
        raise ValidationError("Geometry invalid after transformation.")
    return geom


def save_place(source, key, **values):
    # The source/key pair makes reruns update the same qualified record.
    place = Place.objects.filter(source=source, source_key=key).first()
    created = place is None
    if created:
        place = Place(source=source, source_key=key)
    for field, value in values.items():
        setattr(place, field, value)
    # Model save() does not run validators automatically.
    place.full_clean()
    place.save()
    return created


def entry(row, key, outcome, reason, **extra):
    """Keep each import decision traceable to its original source row."""
    return {"row": row, "source_key": key, "outcome": outcome, "reason": reason, **extra}


def finish(command, slug, metadata, rows, warnings=()):
    # Include the row-level ledger as well as totals so omissions are explainable.
    counts = Counter(item["outcome"] for item in rows)
    imported = [item for item in rows if item["outcome"] == "imported"]
    report = {
        "dataset": slug, "sha256": metadata["sha256"], "source_srid": 4326, "stored_srid": 2157,
        "total": len(rows), "imported": len(imported),
        "created": sum(item["created"] for item in imported),
        "updated": sum(not item["created"] for item in imported),
        "skipped": counts["skipped"], "quarantined": counts["quarantined"],
        "warnings": list(warnings), "records": rows,
    }
    command.stdout.write(json.dumps(report, indent=2, ensure_ascii=True))
