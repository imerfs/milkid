"""Turn a surveyed village drawing (DXF) into the GeoJSON the web map uses.

The drawing is the municipality's survey of Dastgerd. What it contains (found by inspecting the file):

* ``Block_No``       small circle + number: one marker inside each block
* ``mabar``          the street lines; the closed rings they form are the blocks
* ``مرز قطعه22-8``   closed outlines of the surveyed plots
* ``Parcell_No``     the plot number, numbered again from 1 inside every block

In the newest part of the village the plots were numbered but their outlines were never drawn (only the
block is). For those the block area that no drawn plot covers is split between the numbers with a Voronoi
partition and the plots are marked ``kind = "estimated"`` so the map can show them as approximate.

Usage (needs the extras in scripts/gis/requirements.txt; the DWG is first converted to DXF, see docs/gis.md):

    python scripts/gis/build_village_map.py drawing.dxf main/data/gis/dastgerd.geojson --epsg 32640

The module only needs ezdxf/shapely/pyproj here, never on the server: the server reads the GeoJSON this writes.
"""
# pylint: disable=import-error  # shapely and pyproj are only installed where a map is rebuilt (requirements.txt here)
import argparse
import collections
import json
import sys
from pathlib import Path

BLOCK_MARKER_LAYER = 'Block_No'
STREET_LAYER = 'mabar'
PLOT_LAYER = 'مرز قطعه22-8'
PLOT_NUMBER_LAYER = 'Parcell_No'
NEAREST_BLOCK_LIMIT = 120.0          # metres: a plot in no block ring is given to a marker at most this far away
MIN_PLOT_AREA = 2.0                  # square metres: slivers and drawing debris are not plots
MIN_ESTIMATED_AREA = 4.0


def renewal_code(block, number):
    """The plot's renewal code as it is built from the drawing: block number and plot number.

    The drawing carries no other renewal data, so this is the one place to change if the municipality's real
    code format differs (zone prefix, zero padding ...).
    """
    if not block or not number:
        return ''
    return f'{block}-{number}'


def _shapely():
    from shapely.geometry import LineString, MultiPolygon, Point, Polygon
    from shapely.ops import polygonize, unary_union, voronoi_diagram
    from shapely.strtree import STRtree
    return LineString, MultiPolygon, Point, Polygon, polygonize, unary_union, voronoi_diagram, STRtree


def closed_polygons(entities):
    """Valid polygons from closed LWPOLYLINEs (open ones whose ends meet count as closed)."""
    _, _, Point, Polygon, *_ = _shapely()
    for entity in entities:
        points = [(p[0], p[1]) for p in entity.get_points('xy')]
        if len(points) < 3 or not (entity.closed or Point(points[0]).distance(Point(points[-1])) < 0.05):
            continue
        polygon = Polygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty and polygon.area >= MIN_PLOT_AREA and polygon.geom_type == 'Polygon':
            yield polygon


def smallest_containing(tree, polygons, point):
    hits = list(tree.query(point, predicate='within'))
    return min(hits, key=lambda i: polygons[i].area) if hits else None


def build_blocks(street_lines, markers):
    """Blocks are the closed rings the street lines enclose; a ring takes the number of the marker inside it."""
    *_, polygonize, unary_union, _, STRtree = _shapely()
    rings = list(polygonize(unary_union(street_lines)))
    tree = STRtree(rings)
    numbered = {}
    for point, number in markers:
        index = smallest_containing(tree, rings, point)
        if index is not None:
            numbered.setdefault(index, number)
    return [(number, rings[index]) for index, number in numbered.items()]


def assign_block(point, blocks, block_tree, markers):
    """(block number, how it was found) for a point: ring that holds it, else the nearest marker, else None."""
    index = smallest_containing(block_tree, [polygon for _, polygon in blocks], point) if blocks else None
    if index is not None:
        return blocks[index][0], 'ring'
    nearest = min(markers, key=lambda m: m[0].distance(point), default=None)
    if nearest and nearest[0].distance(point) <= NEAREST_BLOCK_LIMIT:
        return nearest[1], 'nearest'
    return None, 'none'


def one_polygon(geometry, point):
    """A single Polygon out of a (Multi)Polygon: the piece holding ``point``, else the biggest one."""
    if geometry.geom_type == 'Polygon':
        return geometry
    pieces = [g for g in getattr(geometry, 'geoms', []) if g.geom_type == 'Polygon']
    return next((g for g in pieces if g.contains(point)), max(pieces, key=lambda g: g.area, default=None))


def estimate_missing_plots(block_polygon, drawn, numbered_points):
    """Split what is left of the block, after the drawn plots, between the numbers that have no outline."""
    _, MultiPolygon, _, Polygon, _, unary_union, voronoi_diagram, _ = _shapely()
    free = block_polygon.difference(unary_union(drawn)) if drawn else block_polygon
    if free.is_empty or not numbered_points:
        return []
    if len(numbered_points) == 1:
        piece = one_polygon(free, numbered_points[0][0])
        return [(numbered_points[0][1], piece)] if piece is not None and piece.area >= MIN_ESTIMATED_AREA else []
    cells = voronoi_diagram(MultiPolygon_points(numbered_points), envelope=block_polygon.buffer(50))
    result = []
    for cell in cells.geoms:
        part = cell.intersection(free)
        if part.is_empty or part.area < MIN_ESTIMATED_AREA:
            continue
        label = next((n for p, n in numbered_points if cell.contains(p)), None)
        if label is None:
            continue
        point = next(p for p, n in numbered_points if n == label)
        part = one_polygon(part, point)
        if part is None:
            continue
        result.append((label, part))
    return result


def MultiPolygon_points(numbered_points):  # noqa: N802  (named like the shapely helper it wraps)
    from shapely.geometry import MultiPoint
    return MultiPoint([p for p, _ in numbered_points])


def build(doc, epsg):
    """Read the DXF document and return the GeoJSON FeatureCollection (WGS84) plus a statistics dict."""
    LineString, _, Point, _, _, _, _, STRtree = _shapely()
    from pyproj import Transformer
    modelspace = doc.modelspace()

    markers = [(Point(e.dxf.insert.x, e.dxf.insert.y), e.dxf.text.strip())
               for e in modelspace.query(f'TEXT[layer=="{BLOCK_MARKER_LAYER}"]')]
    street_lines = []
    for e in modelspace.query(f'LWPOLYLINE[layer=="{STREET_LAYER}"]'):
        points = [(p[0], p[1]) for p in e.get_points('xy')]
        if len(points) >= 2:
            street_lines.append(LineString(points + [points[0]] if e.closed else points))
    for e in modelspace.query(f'LINE[layer=="{STREET_LAYER}"]'):
        street_lines.append(LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]))
    blocks = build_blocks(street_lines, markers)
    block_polygons = [polygon for _, polygon in blocks]
    block_tree = STRtree(block_polygons) if blocks else None

    numbers = [(Point(e.dxf.insert.x, e.dxf.insert.y), e.dxf.text.strip())
               for e in modelspace.query(f'TEXT[layer=="{PLOT_NUMBER_LAYER}"]') if e.dxf.text.strip()]
    plots = list(closed_polygons(modelspace.query(f'LWPOLYLINE[layer=="{PLOT_LAYER}"]')))
    plot_tree = STRtree(plots)

    inside = collections.defaultdict(list)
    loose = []
    for point, number in numbers:
        index = smallest_containing(plot_tree, plots, point)
        (inside[index].append((point, number)) if index is not None else loose.append((point, number)))

    stats = collections.Counter(blocks=len(blocks), numbers=len(numbers))
    records = []                                         # dicts with a projected geometry
    drawn_by_block = collections.defaultdict(list)
    for index, plot in enumerate(plots):
        centre = plot.representative_point()
        block, source = assign_block(centre, blocks, block_tree, markers)
        held = sorted(inside.get(index, []), key=lambda item: item[0].distance(plot.centroid))
        number = held[0][1] if held else ''
        extra = [n for _, n in held[1:] if n != number]
        stats['drawn'] += 1
        stats['drawn_without_number'] += not number
        stats['block_by_' + source] += 1
        records.append(dict(kind='drawn', block=block or '', number=number, other_numbers=extra,
                            block_source=source, geometry=plot))
        if block:
            drawn_by_block[block].append(plot)

    loose_by_block = collections.defaultdict(list)
    for point, number in loose:
        block, _ = assign_block(point, blocks, block_tree, markers)
        if block:
            loose_by_block[block].append((point, number))
        else:
            stats['numbers_without_block'] += 1
    polygon_of = {number: polygon for number, polygon in blocks}
    for block, points in loose_by_block.items():
        polygon = polygon_of.get(block)
        if polygon is None:
            stats['numbers_without_block'] += len(points)
            continue
        for number, geometry in estimate_missing_plots(polygon, drawn_by_block.get(block, []), points):
            stats['estimated'] += 1
            records.append(dict(kind='estimated', block=block, number=number, other_numbers=[],
                                block_source='ring', geometry=geometry))

    to_wgs = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True)

    def ring(coords):
        return [[round(x, 7), round(y, 7)] for x, y in (to_wgs.transform(cx, cy) for cx, cy in coords)]

    def polygon_coords(polygon):
        return [ring(polygon.exterior.coords)] + [ring(r.coords) for r in polygon.interiors]

    counts = collections.Counter((r['block'], r['number']) for r in records if r['block'] and r['number'])
    features = []
    for r in records:
        code = renewal_code(r['block'], r['number'])
        duplicate = bool(code) and counts[(r['block'], r['number'])] > 1
        stats['duplicate_codes'] += duplicate
        features.append({
            'type': 'Feature',
            'properties': {
                'type': 'parcel', 'kind': r['kind'], 'block': r['block'], 'number': r['number'],
                'code': code, 'area': round(r['geometry'].area, 1), 'block_source': r['block_source'],
                'other_numbers': r['other_numbers'], 'duplicate': duplicate,
            },
            'geometry': {'type': 'Polygon', 'coordinates': polygon_coords(r['geometry'])},
        })
    plots_per_block = collections.Counter(r['block'] for r in records if r['block'])
    for number, polygon in sorted(blocks, key=lambda b: (len(b[0]), b[0])):
        features.append({
            'type': 'Feature',
            'properties': {'type': 'block', 'number': number, 'parcels': plots_per_block.get(number, 0),
                           'area': round(polygon.area, 1)},
            'geometry': {'type': 'Polygon', 'coordinates': polygon_coords(polygon)},
        })
    stats['features'] = len(features)
    return {'type': 'FeatureCollection', 'features': features}, dict(stats)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('dxf')
    parser.add_argument('output')
    parser.add_argument('--epsg', type=int, default=32640, help='coordinate system of the drawing (UTM zone 40N)')
    args = parser.parse_args(argv)
    import ezdxf
    sys.stdout.reconfigure(encoding='utf-8')
    collection, stats = build(ezdxf.readfile(args.dxf), args.epsg)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collection, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for key, value in sorted(stats.items()):
        print(f'{key:28} {value}')
    print('written', out, f'{out.stat().st_size / 1e6:.2f} MB')


if __name__ == '__main__':
    main()
