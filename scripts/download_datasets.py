"""Download the qualified snapshots without modifying or importing their contents.

Uses curl (included in macOS) for normal TLS verification. A checksum mismatch
stops setup instead of silently accepting a changed upstream resource.
"""
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def validate(body, filename):
    if body.lstrip().lower().startswith((b'<!doctype', b'<html')):
        raise ValueError('Received HTML instead of source data')
    # Canvas contains malformed UTF-8: surrogateescape is inspection, not repair.
    text = body.decode('utf-8-sig', errors='surrogateescape')
    if filename.endswith('.geojson'):
        data = json.loads(text)
        if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
            raise ValueError('Not a GeoJSON FeatureCollection')
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not {'Latitude', 'Longitude', 'Description'}.issubset(reader.fieldnames or []):
            raise ValueError('Unexpected public-art CSV columns')
        if not list(reader):
            raise ValueError('Empty CSV')


def main():
    destination = ROOT / 'data' / 'raw'
    destination.mkdir(parents=True, exist_ok=True)
    for source in json.loads((ROOT / 'data' / 'sources.json').read_text()):
        path = destination / source['filename']
        if path.exists():
            body = path.read_bytes()
        else:
            body = subprocess.check_output([
                'curl', '--fail', '--silent', '--show-error', '--location',
                '--proto', '=https', '--proto-redir', '=https', '--max-time', '120', source['url'],
            ])
        if hashlib.sha256(body).hexdigest() != source['sha256']:
            raise ValueError(f"Snapshot changed: {source['filename']}; review before updating the manifest")
        validate(body, source['filename'])
        if not path.exists():
            path.write_bytes(body)
        print(f"Verified {source['filename']}: {len(body)} bytes")


if __name__ == '__main__':
    main()
