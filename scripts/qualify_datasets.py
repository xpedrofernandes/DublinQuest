# Inspect source quality and spatial coverage without altering snapshots or database records.
"""Read-only inspection of the four source snapshots using the taught GEOS tools.

Run inside the web image with a read-only dataset mount; no Django/database writes.
Row numbers below are one-based data rows/features (CSV header is not counted).
"""
import csv
import hashlib
import io
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, Point


def duplicates(values):
    # Return source row groups so suspected duplicates can be reviewed in context.
    grouped = defaultdict(list)
    for row, value in values:
        if value not in (None, ''):
            grouped[str(value)].append(row)
    return [rows for rows in grouped.values() if len(rows) > 1]


def inspect(folder):
    results = {}
    points, parks = [], []
    for name, extension in [('canvas', 'geojson'), ('public_art', 'csv'),
                            ('heritage', 'geojson'), ('parks', 'geojson')]:
        raw = (folder / f'{name}.{extension}').read_bytes()
        decode_errors = []
        try:
            text = raw.decode('utf-8-sig')
            encoding = 'UTF-8 (optional BOM)'
        except UnicodeDecodeError:
            # Inspection only: retain malformed byte positions; never silently clean raw data.
            text = raw.decode('utf-8', errors='surrogateescape')
            decode_errors = [{'character_offset': i, 'byte_hex': hex(ord(c) - 0xDC00)}
                             for i, c in enumerate(text) if 0xDC80 <= ord(c) <= 0xDCFF]
            encoding = 'INVALID UTF-8; surrogateescape for structural inspection only'
        if extension == 'geojson':
            data = json.loads(text)
            assert data['type'] == 'FeatureCollection'
            rows = [f.get('properties') or {} for f in data['features']]
            geometries = [f.get('geometry') for f in data['features']]
            crs = data.get('crs')
        else:
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            assert {'Latitude', 'Longitude', 'Description'}.issubset(reader.fieldnames)
            geometries = []
            for row in rows:
                try:
                    geometries.append({'type': 'Point', 'coordinates': [float(row['Longitude']), float(row['Latitude'])]})
                except (ValueError, TypeError):
                    geometries.append(None)
            crs = 'No embedded CRS: named latitude/longitude columns; WGS84 interpretation requires catalogue corroboration'
        # Record field completeness separately from geometric validity.
        fields = sorted(set().union(*(r.keys() for r in rows)))
        missing = {key: sum(r.get(key) is None or str(r.get(key)).strip() == '' for r in rows) for key in fields}
        types = Counter()
        bounds, invalid, absent, bad_coordinates = [], [], [], []
        geometry_keys, projected = [], []
        name_field = {'canvas': 'Artwork title:', 'public_art': 'CultureName ', 'heritage': 'Title', 'parks': 'Name'}[name]
        for index, (row, geometry) in enumerate(zip(rows, geometries), 1):
            if not geometry:
                absent.append(index)
                continue
            types[geometry['type']] += 1
            try:
                geom = GEOSGeometry(json.dumps(geometry), srid=4326)
                extent = geom.extent
                if geom.empty or not all(math.isfinite(v) for v in extent) or not (-180 <= extent[0] <= extent[2] <= 180 and -90 <= extent[1] <= extent[3] <= 90):
                    bad_coordinates.append(index)
                    continue
                bounds.append(extent)
                if not geom.valid:
                    invalid.append({'row': index, 'name': row.get(name_field), 'reason': geom.valid_reason})
                # Normalize only this inspection copy to compare equivalent geometries.
                geom.normalize()
                geometry_keys.append((index, geom.wkb.hex()))
                geom.transform(2157)
                projected.append((index, geom))
                title = str(row.get(name_field) or '').strip()
                if name == 'parks':
                    parks.append((index, title, geom))
                else:
                    points.append((name, index, title, geom, row))
            except (ValueError, TypeError) as error:
                invalid.append({'row': index, 'reason': str(error)})
        # Project the illustrative centre before measuring candidate coverage in metres.
        center = Point(-6.26, 53.35, srid=4326)
        center.transform(2157)
        nearby = {str(radius): sum(geom.distance(center) <= radius for _, geom in projected) for radius in (500, 1000, 2000, 5000)}
        categorical = {key: dict(Counter(str(r.get(key)) for r in rows)) for key in fields if key in ('Council:', 'Status:', 'Year:', 'Typology', 'Class')}
        id_fields = {key: {'missing': missing[key], 'duplicate_groups': duplicates((i, r.get(key)) for i, r in enumerate(rows, 1))}
                     for key in fields if key in ('PRIMARYINDEX', 'Park_ID', 'Website Profile:', 'Website')}
        results[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), encoding=encoding,
            decoding_errors=decode_errors, count=len(rows), fields=fields, missing=missing,
            geometry_types=dict(types), crs=crs, missing_geometry_rows=absent, invalid_geometries=invalid,
            invalid_coordinate_rows=bad_coordinates,
            bounds=[min(b[0] for b in bounds), min(b[1] for b in bounds), max(b[2] for b in bounds), max(b[3] for b in bounds)],
            exact_row_duplicate_groups=duplicates((i,json.dumps({'properties':r,'geometry':geometries[i-1]},sort_keys=True)) for i,r in enumerate(rows,1)),
            geometry_duplicate_groups=duplicates(geometry_keys),
            normalized_name_duplicate_groups=duplicates((i,str(r.get(name_field) or '').strip().casefold()) for i,r in enumerate(rows,1)),
            identifier_checks=id_fields, categories=categorical, within_metres_of_illustrative_center=nearby)
        results[name]['text_quality_candidates'] = [
            {'row': i, 'field': key, 'value': value}
            for i,row in enumerate(rows,1) for key,value in row.items()
            if isinstance(value,str) and any(c in value for c in ('Ã', 'Â', '\ufffd'))]
        results[name]['malformed_utf8_rows'] = [i for i,row in enumerate(rows,1)
            if any(any(0xDC80 <= ord(c) <= 0xDCFF for c in str(value)) for value in row.values())]
        results[name]['placeholder_counts'] = {key: sum(r.get(key) is not None and str(r.get(key)).strip().casefold() in ('n/a','na','none','null','unknown','-') for r in rows) for key in fields}
        if name == 'parks':
            eligible = [(i,g) for i,g in projected if g.valid and str(rows[i-1].get('Name') or '').strip() and rows[i-1].get('Typology') not in ('Institutional Land', 'Graveyards')]
            results[name]['proposed_named_noninstitutional_nongraveyard'] = {'rows':len(eligible), 'intersect_2km_buffer':sum(g.intersects(center.buffer(2000)) for i,g in eligible), 'point_on_surface_within_2km':sum(g.point_on_surface.distance(center) <= 2000 for i,g in eligible)}
        if name == 'heritage':
            results[name]['titles'] = [r.get('Title') for r in rows]
        if name == 'canvas':
            candidates = [(i,g) for i,g in projected if rows[i-1].get('Council:') == 'Dublin City Council' and rows[i-1].get('Status:') == '1. Remain as is' and str(rows[i-1].get(name_field) or '').strip()]
            results[name]['proposed_dcc_remain_counts'] = {'rows':len(candidates), 'unique_points':len({g.wkb.hex() for i,g in candidates}), 'within_2km':sum(g.distance(center) <= 2000 for i,g in candidates)}
            results[name]['dcc_named_geometry_within_2km'] = sum(
                bool(str(r.get(name_field) or '').strip()) and 'Dublin City' in str(r.get('Council:')) and geom.distance(center) <= 2000
                for i,geom in projected for r in [rows[i-1]])
    # Candidates only: repeated names or coordinates are not proof of duplicate attractions.
    name_groups = defaultdict(list)
    for n,i,title,g,r in points:
        if title:
            name_groups[title.casefold()].append((n,i))
    results['cross_source_name_candidates'] = [group for group in name_groups.values() if len({n for n,i in group}) > 1]
    results['cross_source_nearby_candidates'] = []
    for index, first in enumerate(points):
        for second in points[index + 1:]:
            if first[0] == second[0]:
                continue
            distance = first[3].distance(second[3])
            if distance <= 20:
                results['cross_source_nearby_candidates'].append({
                    'a': f'{first[0]}:{first[1]} {first[2]}',
                    'b': f'{second[0]}:{second[1]} {second[2]}',
                    'distance_m': round(distance, 2),
                })
    # Use only valid park boundaries for qualification of containment demonstrations.
    results['park_containment_candidates'] = []
    for row, title, boundary in parks:
        if not boundary.valid:
            continue
        contained = []
        for source, point_row, label, point, properties in points:
            if boundary.covers(point):
                contained.append(f'{source}:{point_row} {label}')
        if contained:
            results['park_containment_candidates'].append({
                'park_row': row, 'name': title,
                'point_count': len(contained), 'examples': contained[:5],
            })
    return results


if __name__ == '__main__':
    print(json.dumps(inspect(Path(sys.argv[1] if len(sys.argv) > 1 else 'data/raw')), indent=2, ensure_ascii=True))
