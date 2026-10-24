# pylint: disable=import-error  # shapely, pyproj and ezdxf are installed only where a map is rebuilt (requirements.txt)
"""Read the detail drawing (DXF) of a village and write the layers around the plots: roads, water, power, trees,
limits and street names, as one GeoJSON the map page loads on demand.

The plot map (blocks, plots, buildings, easements) comes from ``build_village_map.py``; this script adds what that
one leaves out. A layer is taken only when its name says what it is (the drawing's layer names are the plan's own
legend: «راه آسفالته», «کانال آبی», «تیر برق - چراغ روشنایی» ...); layers whose meaning is not clear from the name are
listed in the report and left out, never guessed.

Usage:  python scripts/gis/build_context_layers.py detail.dxf main/data/gis/dastgerd_context.geojson \n            --plots main/data/gis/dastgerd.geojson
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# normalised layer name -> (group, kind). Groups are the tick boxes of the map; kinds are the styles inside one.
RULES = {
    'راه آسفالته14-3': ('roads', 'asphalt'),
    'راه شوسه14-6': ('roads', 'gravel'),
    'راه جيپرو14-5': ('roads', 'jeep'),
    'ax road': ('roads', 'axis'),
    'کانال آبي19-4': ('water', 'channel'),
    'آبريز19-0': ('water', 'drain'),
    'بستر': ('water', 'bed'),
    'bastar': ('water', 'bed'),
    'loole ab shahri': ('water', 'pipe'),
    'خط اتصال لوله آب37-0': ('water', 'pipe'),
    'مخزن آب38-0': ('water', 'tank'),
    'آب انبار23-0': ('water', 'tank'),
    'شير آب55-5': ('water', 'tap'),
    'رشته قنات - چاه آب20-1': ('water', 'qanat'),
    'تير برق - چراغ روشنايي11-2': ('power', 'pole'),
    'تير تلفن11-2-1': ('power', 'phone_pole'),
    'ترانس11-5': ('power', 'transformer'),
    'خط اتصال برق فشار قوی 1-11-2': ('power', 'hv_line'),
    'منهول55-2': ('power', 'manhole'),
    'تک درخت6-0': ('trees', 'tree'),
    'limit-final': ('limits', 'village'),
    'حد10-5': ('limits', 'village'),
    'سيم خاردار10-3': ('limits', 'fence'),
    'divare saheli': ('limits', 'wall'),
    'دام و طيور23-8': ('limits', 'livestock'),
    'تابلو20-0': ('signs', 'sign'),
}
TEXT_LAYERS = {'0txt', 'dim'}
POINT_BLOCK_RADIUS = 4.0          # metres: a circle of the water-tap / well layers is drawn as a point
MIN_TEXT = 2


def normal(name):
    return name.replace('ي', 'ی').replace('ك', 'ک').strip()


RULES = {normal(k): v for k, v in RULES.items()}


def clean_mtext(text):
    """MTEXT with its formatting codes ({\\C0;..}, \\fArial|b0;..) removed."""
    text = re.sub(r'\\[fFcCHhQqWwTtAa][^;]*;', '', text)
    text = text.replace('\\P', ' ').replace('{', '').replace('}', '')
    return re.sub(r'\s+', ' ', text).strip()


def flat(entity, tolerance=0.4):
    """Points of a line-like entity as [(x, y)], arcs and bulges flattened to ``tolerance`` metres."""
    kind = entity.dxftype()
    if kind == 'LINE':
        return [tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]]
    if kind in ('LWPOLYLINE', 'POLYLINE', 'ARC', 'ELLIPSE', 'CIRCLE'):
        try:
            return [(p.x, p.y) for p in ezpath.make_path(entity).flattening(tolerance)]
        except Exception:                                                        # a damaged entity is skipped
            return []
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf')
    parser.add_argument('output')
    parser.add_argument('--plots', help='the village GeoJSON; anything farther than 600 m from its plots is a stray (title block, legend)')
    args = parser.parse_args()

    to_lonlat = Transformer.from_crs('EPSG:32640', 'EPSG:4326', always_xy=True)

    def lonlat(x, y):
        lon, lat = to_lonlat.transform(x, y)
        return [round(lon, 7), round(lat, 7)]

    area = None
    if args.plots:
        xs, ys = [], []
        for f in json.loads(Path(args.plots).read_text(encoding='utf-8'))['features']:
            if f['properties']['type'] == 'block':
                ring = f['geometry']['coordinates'][0] if f['geometry']['type'] == 'Polygon' else f['geometry']['coordinates'][0][0]
                xs += [p[0] for p in ring]
                ys += [p[1] for p in ring]
        pad = 0.0065
        area = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def inside(coords):
        if area is None:
            return True
        while isinstance(coords[0], list):
            coords = coords[0]
        return area[0] <= coords[0] <= area[2] and area[1] <= coords[1] <= area[3]

    doc = ezdxf.readfile(args.dxf)
    features, skipped, counts = [], Counter(), Counter()
    for e in doc.modelspace():
        layer = normal(e.dxf.layer)
        kind = e.dxftype()
        if layer in TEXT_LAYERS and kind in ('TEXT', 'MTEXT'):
            raw = e.dxf.text if kind == 'TEXT' else e.text
            text = clean_mtext(raw)
            if len(text) < MIN_TEXT or not re.search('[؀-ۿ]', text) or any(ord(c) > 0x7F and not ('؀' <= c <= 'ۿ') for c in text):
                skipped['text:' + layer] += 1            # numbers and legacy-encoded strings are not street names
                continue
            x, y = tuple(e.dxf.insert)[:2]
            if not inside(lonlat(x, y)):
                skipped['outside:names'] += 1
                continue
            features.append({'type': 'Feature', 'properties': {'g': 'names', 'k': 'street', 'name': text,
                                                               'rot': round(float(getattr(e.dxf, 'rotation', 0) or 0), 1),
                                                               'h': round(float(getattr(e.dxf, 'height', None) or getattr(e.dxf, 'char_height', 0) or 0), 2)},
                             'geometry': {'type': 'Point', 'coordinates': lonlat(x, y)}})
            counts['names'] += 1
            continue
        rule = RULES.get(layer)
        if rule is None:
            continue
        group, style = rule
        props = {'g': group, 'k': style}
        if kind == 'INSERT':
            x, y = tuple(e.dxf.insert)[:2]
            props['rot'] = round(float(e.dxf.rotation or 0), 1)
            geometry = {'type': 'Point', 'coordinates': lonlat(x, y)}
        elif kind == 'POINT':
            x, y = tuple(e.dxf.location)[:2]
            geometry = {'type': 'Point', 'coordinates': lonlat(x, y)}
        elif kind == 'CIRCLE' and e.dxf.radius <= POINT_BLOCK_RADIUS:
            x, y = tuple(e.dxf.center)[:2]
            geometry = {'type': 'Point', 'coordinates': lonlat(x, y)}
        else:
            points = flat(e)
            if len(points) < 2:
                skipped['empty:' + layer] += 1
                continue
            closed = (kind == 'LWPOLYLINE' and e.closed) or (kind == 'POLYLINE' and e.is_closed) or points[0] == points[-1]
            coords = [lonlat(x, y) for x, y in points]
            if closed and len(coords) >= 4 and style in ('village', 'tank', 'livestock', 'bed'):
                geometry = {'type': 'Polygon', 'coordinates': [coords + ([coords[0]] if coords[0] != coords[-1] else [])]}
            else:
                geometry = {'type': 'LineString', 'coordinates': coords}
        if not inside(geometry['coordinates']):
            skipped['outside:' + group] += 1
            continue
        features.append({'type': 'Feature', 'properties': props, 'geometry': geometry})
        counts[f'{group}/{style}'] += 1

    out = {'type': 'FeatureCollection', 'source': Path(args.dxf).name, 'features': features}
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(features)} features -> {args.output} ({Path(args.output).stat().st_size / 1e6:.2f} MB)')
    for name, n in sorted(counts.items()):
        print(f'  {name}: {n}')
    if skipped:
        print('skipped:', dict(skipped))


if __name__ == '__main__':
    main()
