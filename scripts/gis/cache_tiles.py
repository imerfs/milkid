"""Download the satellite picture of one village into main/data/gis/tiles/ so the map never calls a foreign tile server.

The server is in Iran and Esri / Google refuse Iranian addresses, so imagery is fetched once, from a machine that can reach the provider, and
served by Django from disk (main/gis/tiles.py). Only the village's own area is fetched (a few hundred tiles, a few MB). Standard library only.

    python scripts/gis/cache_tiles.py dastgerd                      # Esri World Imagery, zoom 13-18
    python scripts/gis/cache_tiles.py dastgerd --url 'https://.../{z}/{x}/{y}.jpg' --max-zoom 19

Mind the provider's terms: Esri's imagery needs the attribution that the map shows; some providers (Google among them) do not allow keeping copies.
Re-running only fetches what is missing.
"""
import argparse
import json
import os
import math
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('MELKID_GIS_DATA') or ROOT / 'main' / 'data' / 'gis')
ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'


def bounds(slug):
    xs, ys = [], []

    def walk(coords):
        if isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for item in coords:
                walk(item)

    for feature in json.loads((DATA / f'{slug}.geojson').read_text(encoding='utf-8'))['features']:
        walk(feature['geometry']['coordinates'])
    return min(xs), min(ys), max(xs), max(ys)


def tile_of(lng, lat, zoom):
    n = 2 ** zoom
    return int((lng + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def fetch(url, attempts=3):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'MelkID village map tile cache (municipal use)'})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except OSError:
            time.sleep(1 + attempt)
    return None


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('slug')
    parser.add_argument('--url', default=ESRI, help='tile URL with {z} {x} {y}')
    parser.add_argument('--layer', default='satellite')
    parser.add_argument('--min-zoom', type=int, default=13)
    parser.add_argument('--max-zoom', type=int, default=18)
    parser.add_argument('--pad', type=int, default=1, help='extra tiles around the village')
    args = parser.parse_args(argv)
    west, south, east, north = bounds(args.slug)
    done = fetched = failed = 0
    for zoom in range(args.min_zoom, args.max_zoom + 1):
        x0, y1 = tile_of(west, south, zoom)
        x1, y0 = tile_of(east, north, zoom)
        for x in range(x0 - args.pad, x1 + args.pad + 1):
            for y in range(y0 - args.pad, y1 + args.pad + 1):
                path = DATA / 'tiles' / args.slug / args.layer / str(zoom) / str(x) / f'{y}.jpg'
                done += 1
                if path.exists():
                    continue
                data = fetch(args.url.format(z=zoom, x=x, y=y))
                if not data:
                    failed += 1
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                fetched += 1
                time.sleep(0.05)
        print(f'zoom {zoom}: done', flush=True)
    print(f'{done} tiles wanted, {fetched} downloaded, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
