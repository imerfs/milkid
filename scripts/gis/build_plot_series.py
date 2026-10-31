# pylint: disable=import-error  # shapely, pyproj and ezdxf are installed only where a map is rebuilt (scripts/gis/requirements.txt)
"""Build one «series» of plot numbers (a subdivision whose plots are numbered 1, 2, 3 ... on their own) from a drawing.

The plot outlines are the lines of one layer inside a box (a drawing may hold several copies of the same plan side by side); every outline holding exactly
one number text becomes a plot. Output: ``main/data/gis/<slug>_series_<key>.geojson`` (lon/lat), read by ``main.gis.series`` and loaded with the village map.

Usage: python scripts/gis/build_plot_series.py <file.dxf> <slug> <key> --layer tafkek --box xmin ymin xmax ymax [--text-height 0.85]
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from ezdxf.addons import iterdxf
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

DATA_DIR = Path(__file__).resolve().parent.parent.parent / 'main' / 'data' / 'gis'
TO_LONLAT = Transformer.from_crs('EPSG:32640', 'EPSG:4326', always_xy=True)   # UTM 40N, as in the other drawings
GAP = 0.4                                                                      # metres a drawing may leave open between two lines of one outline
MIN_AREA, MAX_AREA = 30.0, 4000.0                                             # square metres: neither a sliver nor a block
_NUMBER = re.compile(r'\d{1,4}')
_CODES = re.compile(r'\\[A-Za-z][^;]*;|[{}]')


def read(path, layer, box, height):
    """The outline segments and the (number, point) texts of ``layer`` inside ``box``."""
    x0, y0, x1, y1 = box
    inside = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
    segments, numbers = [], []
    for entity in iterdxf.single_pass_modelspace(open(path, 'rb')):
        if entity.dxf.layer != layer:
            continue
        kind = entity.dxftype()
        if kind == 'LINE':
            a, b = entity.dxf.start, entity.dxf.end
            if inside(a.x, a.y) and inside(b.x, b.y):
                segments.append(LineString([(a.x, a.y), (b.x, b.y)]))
        elif kind == 'LWPOLYLINE':
            pts = [(p[0], p[1]) for p in entity.get_points('xy')]
            if entity.is_closed:
                pts.append(pts[0])
            if len(pts) > 1 and all(inside(x, y) for x, y in pts):
                segments.append(LineString(pts))
        elif kind in ('TEXT', 'MTEXT'):
            text = entity.dxf.text if kind == 'TEXT' else entity.text
            text = _CODES.sub('', text).strip()
            at = entity.dxf.insert
            size = entity.dxf.height if kind == 'TEXT' else entity.dxf.char_height
            if _NUMBER.fullmatch(text) and abs(size - height) < 0.01 and inside(at.x, at.y):
                numbers.append((str(int(text)), Point(at.x, at.y)))
    return segments, numbers


def closed_cells(segments, gap):
    """Outlines whose lines miss each other by up to ``gap`` metres: the holes of the lines thickened by half of it."""
    thick = unary_union([s.buffer(gap / 2) for s in segments])
    parts = thick.geoms if hasattr(thick, 'geoms') else [thick]
    return [Polygon(ring).buffer(gap / 2) for part in parts for ring in part.interiors]


def build(segments, numbers):
    """Plots = outlines that hold exactly one number. Returns (plots, stats)."""
    outlines = [p for p in polygonize(unary_union(segments)) if MIN_AREA <= p.area <= MAX_AREA]
    outlines += [p for p in closed_cells(segments, GAP) if MIN_AREA <= p.area <= MAX_AREA]
    outlines = [p for p in outlines if p.geom_type == 'Polygon']
    tree = STRtree(outlines)
    held, lost = {}, 0
    for number, point in numbers:                                       # the smallest outline round a number is its plot
        around = [i for i in tree.query(point) if outlines[i].contains(point)]
        if not around:
            lost += 1
            continue
        held.setdefault(min(around, key=lambda i: outlines[i].area), []).append(number)
    plots, skipped = [], Counter()
    for index, found in held.items():
        if len(found) != 1:
            skipped['outline holds several numbers'] += 1
            continue
        plots.append((found[0], outlines[index]))
    skipped['number outside every outline'] = lost
    return plots, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf')
    parser.add_argument('slug')
    parser.add_argument('key')
    parser.add_argument('--layer', default='tafkek')
    parser.add_argument('--box', nargs=4, type=float, required=True, metavar=('XMIN', 'YMIN', 'XMAX', 'YMAX'))
    parser.add_argument('--text-height', type=float, default=0.85)
    args = parser.parse_args()
    segments, numbers = read(args.dxf, args.layer, args.box, args.text_height)
    plots, skipped = build(segments, numbers)
    counts = Counter(number for number, _ in plots)
    features = []
    for number, polygon in sorted(plots, key=lambda item: (int(item[0]), item[1].centroid.y)):
        ring = [[round(x, 7), round(y, 7)] for x, y in (TO_LONLAT.transform(*p) for p in polygon.exterior.coords)]
        features.append({'type': 'Feature', 'properties': {'number': number, 'area': round(polygon.area, 1), 'repeated': counts[number] > 1},
                         'geometry': {'type': 'Polygon', 'coordinates': [ring]}})
    out = DATA_DIR / f'{args.slug}_series_{args.key}.geojson'
    out.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False), encoding='utf-8')
    print(f'{len(segments)} segments, {len(numbers)} numbers -> {len(features)} plots ({sum(1 for c in counts.values() if c > 1)} numbers repeated), skipped {dict(skipped)}')
    print(f'numbers {min(int(n) for n in counts)}..{max(int(n) for n in counts)} written to {out}')


if __name__ == '__main__':
    main()
