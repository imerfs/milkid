# pylint: disable=import-error  # ezdxf and pyproj are installed only where a map is rebuilt (requirements.txt)
"""Turn the detail drawing (DXF) into the cartographic base layer of the web map: the plan as it looks in AutoCAD.

Everything the drawing draws inside the village is written with its own colour, line weight and line type: filled and
pattern-hatched areas (land-use zones, roads, parks, building hatches), lines, polylines, arcs, circles and the plan's
texts. The map page draws it on a canvas (static/js/village-cad.js), so the web map shows the same plan the planners
see instead of a re-interpretation of it.

Layers that are off or frozen in the drawing are left out, so are the title block and legend outside the village
(anything farther than ~600 m from the plots). Texts in the legacy Persian SHX encoding are decoded with
scripts/gis/shx_text.py; a text that still has unknown bytes is dropped, never shown garbled.

Usage:  python scripts/gis/build_cad_layer.py detail.dxf main/data/gis/dastgerd_cad.json --plots main/data/gis/dastgerd.geojson
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from ezdxf.colors import DXF_DEFAULT_COLORS, int2rgb
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import shx_text  # noqa: E402  pylint: disable=wrong-import-position

SKIP_LAYERS = {'defpoints', 'parcel_no', 'point', 'uc'}
SKIP_TEXTS = {'عز'}                  # 563 copies of the survey's marker on the plots (the letters 'uc'), not a label
HATCH_KINDS = {                      # pattern name -> (kind, base angle in degrees)
    'SOLID': ('s', 0), '_SOLID': ('s', 0),
    'ANSI31': ('l', 45), 'ANSI32': ('l', 45), 'ANSI33': ('l', 45), 'ANSI34': ('l', 45), 'ANSI35': ('l', 45),
    'LINE': ('l', 0), 'DASH': ('l', 0), 'ANGLE': ('l', 45), 'ANSI36': ('l', 45),
    'ANSI37': ('x', 45), 'ANSI38': ('x', 45), 'NET': ('x', 0), 'NET3': ('x', 45), 'HEX': ('x', 0),
    'GRAVEL': ('o', 0), 'STARS': ('o', 0), 'GRASS': ('o', 0), 'HOUND': ('o', 0), 'AR-CONC': ('o', 0), 'DOTS': ('o', 0),
}
MIN_SPACING_M = 0.4
MAX_SPACING_M = 40.0


def normal(name):
    return name.replace('ي', 'ی').replace('ك', 'ک').strip()


def hex_of(rgb):
    return '#%02x%02x%02x' % tuple(rgb)


def layer_color(layer):
    if layer.has_dxf_attrib('true_color'):
        return hex_of(int2rgb(layer.dxf.true_color))
    return hex_of(int2rgb(DXF_DEFAULT_COLORS[abs(layer.dxf.color) % 256 or 7]))


def entity_color(e, layer_hex):
    if e.dxf.hasattr('true_color'):
        return hex_of(int2rgb(e.dxf.true_color))
    aci = e.dxf.get('color', 256)
    if aci in (0, 256) or aci > 255:
        return layer_hex
    return hex_of(int2rgb(DXF_DEFAULT_COLORS[aci]))


def weight_px(e, layer):
    value = e.dxf.get('lineweight', -1)
    if value < 0:
        value = layer.dxf.get('lineweight', -3)
    if value < 0:
        value = 25
    return round(min(max(value / 25.0, 0.6), 4.0), 1)


def dash_of(e, layer):
    name = (e.dxf.get('linetype', 'BYLAYER') or 'BYLAYER').upper()
    if name in ('BYLAYER', 'BYBLOCK'):
        name = (layer.dxf.get('linetype', 'CONTINUOUS') or 'CONTINUOUS').upper()
    if 'DASHDOT' in name or 'CENTER' in name or 'PHANTOM' in name:
        return 'c'
    if 'DASH' in name or 'HIDDEN' in name:
        return 'd'
    if 'DOT' in name:
        return 'o'
    return ''


def clean_mtext(text):
    text = re.sub(r'\\[fFcCHhQqWwTtAa][^;]*;', '', text)
    text = text.replace('\\P', ' ').replace('{', '').replace('}', '')
    # only plain blanks collapse: the legacy Persian font stores letters in U+00A0 and U+0085, which \s would erase
    return re.sub(r'[ \t\r\n]+', ' ', text).strip(' \t\r\n')


def readable(text):
    """The text as Unicode Persian, a number, or None when it is garbage or has bytes the SHX table does not know.

    A real Unicode string has Persian letters and no ASCII letters or stray punctuation (the legacy encoding puts
    Persian letters on the ASCII keys, so ``,v,nچ`` is a mis-encoded word, not text).
    """
    persian = re.compile(r'[؀-ۿ]')
    stray = re.compile(r'[A-Za-z\u0080-\u00FF\u0100-\u02FF\u2000-\u200B\u200D-\u206F\u0600-\u0605\u0610-\u061F\u066A-\u066D\u06D4\u06DD\u06DE\u06E9]')
    if not text:
        return None
    if persian.search(text) and not stray.search(text):
        return text
    if re.fullmatch(r'[\d\s./:+\-()%]+', text):
        return text
    decoded = shx_text.read(text)
    if '<' in decoded or not persian.search(decoded) or stray.search(decoded):
        return None
    return decoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf')
    parser.add_argument('output')
    parser.add_argument('--plots', required=True)
    args = parser.parse_args()

    to_lonlat = Transformer.from_crs('EPSG:32640', 'EPSG:4326', always_xy=True)
    xs, ys = [], []
    for f in json.loads(Path(args.plots).read_text(encoding='utf-8'))['features']:
        if f['properties']['type'] == 'block':
            ring = f['geometry']['coordinates'][0] if f['geometry']['type'] == 'Polygon' else f['geometry']['coordinates'][0][0]
            xs += [p[0] for p in ring]
            ys += [p[1] for p in ring]
    pad = 0.0065
    area = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def ll(x, y):
        lon, lat = to_lonlat.transform(x, y)
        return round(lon, 6), round(lat, 6)

    def inside(lon, lat):
        return area[0] <= lon <= area[2] and area[1] <= lat <= area[3]

    def flat_coords(points):
        out = []
        for x, y in points:
            out.extend(ll(x, y))
        return out

    doc = ezdxf.readfile(args.dxf)
    layers, layer_index, layer_meta = {}, {}, []
    for layer in doc.layers:
        name = normal(layer.dxf.name)
        layers[name] = layer

    def index_of(name):
        if name not in layer_index:
            layer_index[name] = len(layer_meta)
            layer_meta.append({'n': name, 'c': layer_color(layers[name]) if name in layers else '#ffffff'})
        return layer_index[name]

    hatches, lines, texts = [], [], []
    stats, skipped = Counter(), Counter()
    for e in doc.modelspace():
        kind = e.dxftype()
        name = normal(e.dxf.layer)
        layer = layers.get(name)
        if layer is None or name.lower() in SKIP_LAYERS or not layer.is_on() or layer.is_frozen():
            skipped['layer'] += 1
            continue
        base = layer_color(layer)
        color = entity_color(e, base)
        try:
            if kind == 'HATCH':
                rings = []
                for sub in ezpath.from_hatch(e):
                    pts = [(p.x, p.y) for p in sub.flattening(0.5)]
                    if len(pts) >= 3:
                        rings.append(flat_coords(pts))
                if not rings or not inside(rings[0][0], rings[0][1]):
                    skipped['outside'] += 1
                    continue
                pattern = (e.dxf.pattern_name or 'SOLID').upper()
                if e.dxf.solid_fill:
                    pattern = 'SOLID'
                pkind, base_angle = HATCH_KINDS.get(pattern, ('l', 45))
                item = {'k': 'h', 'l': index_of(name), 'r': rings}
                if color != base:
                    item['c'] = color
                if pkind != 's':
                    spacing = min(max(3.175 * float(e.dxf.get('pattern_scale', 1.0) or 1.0), MIN_SPACING_M), MAX_SPACING_M)
                    item.update(p=pkind, a=round((base_angle + float(e.dxf.get('pattern_angle', 0.0) or 0.0)) % 180, 1),
                                s=round(spacing, 2))
                hatches.append(item)
                stats['hatch'] += 1
            elif kind in ('LWPOLYLINE', 'POLYLINE', 'LINE', 'ARC', 'CIRCLE', 'ELLIPSE'):
                if kind == 'LINE':
                    pts = [tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]]
                else:
                    pts = [(p.x, p.y) for p in ezpath.make_path(e).flattening(0.4)]
                if len(pts) < 2:
                    continue
                coords = flat_coords(pts)
                if not inside(coords[0], coords[1]):
                    skipped['outside'] += 1
                    continue
                item = {'k': 'l', 'l': index_of(name), 'p': coords}
                if color != base:
                    item['c'] = color
                w, d = weight_px(e, layer), dash_of(e, layer)
                if w != 1.0:
                    item['w'] = w
                if d:
                    item['d'] = d
                lines.append(item)
                stats['line'] += 1
            elif kind in ('TEXT', 'MTEXT'):
                text = readable(clean_mtext(e.dxf.text if kind == 'TEXT' else e.text))
                if not text or text in SKIP_TEXTS:
                    skipped['text'] += 1
                    continue
                x, y = tuple(e.dxf.insert)[:2]
                lon, lat = ll(x, y)
                if not inside(lon, lat):
                    skipped['outside'] += 1
                    continue
                height = float(e.dxf.char_height if kind == 'MTEXT' else e.dxf.height)
                if height <= 0:
                    continue
                item = {'k': 't', 'l': index_of(name), 's': text, 'x': lon, 'y': lat, 'h': round(height, 2),
                        'a': round(float(e.get_rotation() if kind == 'MTEXT' else (e.dxf.rotation or 0)), 1)}
                if color != base:
                    item['c'] = color
                texts.append(item)
                stats['text'] += 1
        except Exception as exc:                             # one damaged entity must not stop the rebuild
            skipped[f'error:{kind}:{type(exc).__name__}'] += 1

    solid_first = sorted(hatches, key=lambda h: 'p' in h)       # fills below pattern hatches
    out = {'source': Path(args.dxf).name, 'layers': layer_meta, 'items': solid_first + lines + texts}
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(out["items"])} items -> {args.output} ({Path(args.output).stat().st_size / 1e6:.2f} MB)', dict(stats), 'skipped', dict(skipped))


if __name__ == '__main__':
    main()
