# pylint: disable=import-error  # shapely and pyproj are only installed where a map is rebuilt (requirements.txt here)
"""Turn the village's surveyed drawings (DXF) into the GeoJSON the web map uses.

Two drawings of Dastgerd are used:

* the **survey** (1404, ``join14040110``) numbers everything: ``Block_No`` markers, ``mabar`` street lines whose
  closed rings are the blocks, ``مرز قطعه22-8`` plot outlines and ``Parcell_No`` plot numbers;
* the **detail drawing** (1405, ``Pish-Dastgerd``) has the coloured land-use hatches, the easements (حریم) and the
  building footprints. Its coordinates are the same (UTM zone 40N).

In the newest part of the village the plots were numbered but their outlines were never drawn (only the block is).
For those the block area that no drawn plot covers is split between the numbers with a Voronoi partition and the
plots are marked ``kind = "estimated"`` so the map can show them as approximate.

The neighbourhood (محله) of every block comes from the picture the municipality made of its five neighbourhoods:
scripts/gis/georef_zones.py registers it on the plots and writes the zones file this script reads.

Usage (the extras are in scripts/gis/requirements.txt; DWG -> DXF first, see docs/gis.md):

    python scripts/gis/build_village_map.py survey.dxf main/data/gis/dastgerd.geojson \
        --detail-dxf detail.dxf --zones main/data/gis/dastgerd_zones.json

shapely, pyproj and ezdxf are needed here only, never on the server: the server reads the GeoJSON this writes.
"""
import argparse
import collections
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from main.gis.uids import parcel_uids, renewal_code  # noqa: E402  pylint: disable=wrong-import-position

BLOCK_MARKER_LAYER = 'Block_No'
STREET_LAYER = 'mabar'
PLOT_LAYER = 'مرز قطعه22-8'
PLOT_NUMBER_LAYER = 'Parcell_No'
BUILDING_LAYER = 'l.building'
NO_FILL_LAYERS = {BUILDING_LAYER, 'h.building', 'پروانه'}   # patterns on buildings and the permit marks, not land use
NEAREST_BLOCK_LIMIT = 120.0          # metres: a plot in no block ring is given to a marker at most this far away
MIN_PLOT_AREA = 2.0                  # square metres: slivers and drawing debris are not plots
MIN_ESTIMATED_AREA = 4.0
MIN_EASEMENT_OVERLAP = 1.0           # square metres of a plot inside an easement before it counts as a violation
HOUSING_BBOX = (713050.0, 3645020.0, 714250.0, 3646240.0)   # where the housing area lies (UTM metres)
CORRIDOR_PAIR_LIMIT = 70.0           # metres: two easement lines this close are the two sides of one corridor

# Easement layers of the detail drawing -> (kind, label). The kind is what the map's tick boxes switch.
EASEMENT_LAYERS = {
    'Harim': ('general', 'حریم'),
    'حریم کیفی': ('quality', 'حریم کیفی'),
    'harime ghanat': ('qanat', 'حریم قنات'),
    'harim keifi ghanet': ('qanat_quality', 'حریم کیفی قنات'),
    'harim padafand 1': ('defense1', 'حریم پدافند غیرعامل (۱)'),
    'harim padafand 2': ('defense2', 'حریم پدافند غیرعامل (۲)'),
}

# What each fill colour of the detail drawing is. Only yellow is certain (the residential fill under 2 190 plots,
# which also carry the residential building polygons); the other colours are named once the drawing's legend is read.
LAND_USE_NAMES = {'ffff00': 'مسکونی'}

# The master plan's legend (read from its legacy Persian font, see scripts/gis/shx_text.py) numbers its land uses, and
# the hatch layers carry the number: layer "27hp" is use 27. Only the numbers the legend lists are named.
LAND_USE_CODES = {
    1: 'مسکونی', 2: 'تجاری', 5: 'آموزشی (دبستان)', 6: 'آموزشی (متوسطه اول)', 7: 'آموزشی (متوسطه دوم)',
    10: 'فرهنگی', 12: 'مذهبی', 14: 'اداری', 16: 'تأسیسات و تجهیزات', 19: 'درمانی (درمانگاه)',
    20: 'درمانی (خانه بهداشت)', 27: 'جهانگردی و پذیرایی', 28: 'ورزشی - تفریحی', 31: 'پارک و فضای سبز',
    32: 'فضای سبز عمومی',
}


def land_use_name(layer):
    """The legend's name for a hatch layer such as '1p', '2 hp' or '27hp', or '' when its number is not in the legend."""
    digits = ''.join(itertools.takewhile(str.isdigit, layer.strip()))
    return LAND_USE_CODES.get(int(digits), '') if digits else ''


def _shapely():
    from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon
    from shapely.ops import polygonize, unary_union, voronoi_diagram
    from shapely.strtree import STRtree
    return LineString, MultiPoint, MultiPolygon, Point, Polygon, polygonize, unary_union, voronoi_diagram, STRtree


def closed_polygons(entities, min_area=MIN_PLOT_AREA):
    """Valid polygons from closed LWPOLYLINEs (open ones whose ends meet count as closed)."""
    _, _, _, Point, Polygon, *_ = _shapely()
    for entity in entities:
        points = [(p[0], p[1]) for p in entity.get_points('xy')]
        if len(points) < 3 or not (entity.closed or Point(points[0]).distance(Point(points[-1])) < 0.05):
            continue
        polygon = Polygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty and polygon.area >= min_area and polygon.geom_type == 'Polygon':
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
    _, MultiPoint, _, _, _, _, unary_union, voronoi_diagram, _ = _shapely()
    free = block_polygon.difference(unary_union(drawn)) if drawn else block_polygon
    if free.is_empty or not numbered_points:
        return []
    if len(numbered_points) == 1:
        piece = one_polygon(free, numbered_points[0][0])
        return [(numbered_points[0][1], piece)] if piece is not None and piece.area >= MIN_ESTIMATED_AREA else []
    cells = voronoi_diagram(MultiPoint([p for p, _ in numbered_points]), envelope=block_polygon.buffer(50))
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


# ---------- the detail drawing: land use, buildings, easements ----------

def hatch_fills(modelspace, layers):
    """(polygon, layer, rgb hex, solid) for every land-use hatch of the detail drawing."""
    from ezdxf import path as ezpath
    from ezdxf.colors import aci2rgb
    _, _, _, _, Polygon, *_ = _shapely()
    fills = []
    for hatch in modelspace.query('HATCH'):
        layer = hatch.dxf.layer
        if layer in NO_FILL_LAYERS:
            continue
        true_color = hatch.dxf.get('true_color')
        if true_color is not None:
            rgb = ((true_color >> 16) & 255, (true_color >> 8) & 255, true_color & 255)
        else:
            aci = hatch.dxf.get('color', 256)
            rgb = tuple(aci2rgb(layers.get(layer).color if aci in (None, 256, 0) else aci))
        try:
            paths = ezpath.from_hatch(hatch)
        except Exception:  # pylint: disable=broad-except  # a damaged hatch must not stop the build
            continue
        for path in paths:
            points = [(v.x, v.y) for v in path.flattening(0.05)]
            if len(points) < 3:
                continue
            polygon = Polygon(points)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if polygon.geom_type == 'Polygon' and polygon.area > 0.5:
                fills.append((polygon, layer, '%02x%02x%02x' % rgb, bool(hatch.dxf.solid_fill)))
    return fills


def land_use_of(point, fills, tree):
    """(rgb hex, layer) of the most specific solid fill under ``point`` (any fill if none is solid), else None."""
    hits = [fills[i] for i in tree.query(point, predicate='within')]
    solid = [h for h in hits if h[3]]
    pick = min(solid or hits, key=lambda h: h[0].area) if hits else None
    return (pick[2], pick[1]) if pick else None


def easement_shapes(entities):
    """(polygons, lines) of one easement layer: hatches and closed outlines are areas; open lines that run side
    by side (the two edges of a corridor) are joined into a corridor polygon, the rest stay lines."""
    from ezdxf import path as ezpath
    LineString, _, _, _, Polygon, *_ = _shapely()
    polygons, lines = [], []
    for entity in entities:
        kind = entity.dxftype()
        if kind == 'HATCH':
            try:
                for path in ezpath.from_hatch(entity):
                    points = [(v.x, v.y) for v in path.flattening(0.05)]
                    if len(points) >= 3:
                        polygon = Polygon(points).buffer(0)
                        if polygon.geom_type == 'Polygon' and polygon.area > 1:
                            polygons.append(polygon)
            except Exception:  # pylint: disable=broad-except
                continue
        elif kind in ('LWPOLYLINE', 'POLYLINE'):
            points = ([(p[0], p[1]) for p in entity.get_points('xy')] if kind == 'LWPOLYLINE'
                      else [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices])
            if len(points) < 2:
                continue
            closed = kind == 'LWPOLYLINE' and entity.closed or points[0] == points[-1]
            if closed and len(points) >= 3:
                polygon = Polygon(points).buffer(0)
                if polygon.geom_type == 'Polygon' and polygon.area > 1:
                    polygons.append(polygon)
            else:
                lines.append(LineString(points))
    corridors, rest = pair_corridors(lines)
    return polygons + corridors, rest


def pair_corridors(lines):
    """Join each long line with the line running beside it into a corridor polygon (nothing is invented: the
    corridor is exactly the area between the two drawn edges). Returns (corridors, lines left over)."""
    _, _, _, _, Polygon, *_ = _shapely()
    long_lines = [(i, ln) for i, ln in enumerate(lines) if ln.length >= 20]
    used, corridors = set(), []
    for i, a in long_lines:
        if i in used:
            continue
        candidates = [(a.hausdorff_distance(b), j, b) for j, b in long_lines if j != i and j not in used]
        near = [c for c in candidates if c[0] <= CORRIDOR_PAIR_LIMIT]
        if not near:
            continue
        best = min(near, key=lambda c: c[0])
        _, j, b = best
        ring = list(a.coords) + list(reversed(list(b.coords)))
        polygon = Polygon(ring)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.geom_type == 'Polygon' and polygon.area > 1:
            corridors.append(polygon)
            used.update((i, j))
    return corridors, [ln for i, ln in enumerate(lines) if i not in used]


# ---------- GeoJSON ----------

def geometry_json(geometry, transform):
    """GeoJSON of a shapely geometry (Polygon, MultiPolygon, LineString) reprojected with ``transform``."""
    def ring(coords):
        return [[round(x, 7), round(y, 7)] for x, y in (transform(cx, cy) for cx, cy in coords)]

    def polygon_coords(polygon):
        return [ring(polygon.exterior.coords)] + [ring(r.coords) for r in polygon.interiors]

    if geometry.geom_type == 'Polygon':
        return {'type': 'Polygon', 'coordinates': polygon_coords(geometry)}
    if geometry.geom_type == 'MultiPolygon':
        return {'type': 'MultiPolygon', 'coordinates': [polygon_coords(g) for g in geometry.geoms]}
    return {'type': 'LineString', 'coordinates': ring(geometry.coords)}


def build(survey_doc, epsg, detail_doc=None, zones=None, survey_year=1404, detail_year=1405, housing_doc=None):
    """Return (GeoJSON FeatureCollection in WGS84, statistics) from the survey and, optionally, the detail drawing."""
    LineString, _, _, Point, _, _, unary_union, _, STRtree = _shapely()
    from pyproj import Transformer
    modelspace = survey_doc.modelspace()
    zones = zones or {'blocks': {}, 'plots': {}}

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
    polygon_of = dict(blocks)
    for block, points in loose_by_block.items():
        polygon = polygon_of.get(block)
        if polygon is None:
            stats['numbers_without_block'] += len(points)
            continue
        for number, geometry in estimate_missing_plots(polygon, drawn_by_block.get(block, []), points):
            stats['estimated'] += 1
            records.append(dict(kind='estimated', block=block, number=number, other_numbers=[],
                                block_source='ring', geometry=geometry))

    # --- the housing area (neighbourhood 6): plots built from subdivision lines, with their own block numbers ---
    housing_blocks = []
    if housing_doc is not None:
        from scripts.gis import housing_area
        housing_fills = hatch_fills(housing_doc.modelspace(), housing_doc.layers)
        housing_tree = STRtree([f[0] for f in housing_fills]) if housing_fills else None
        new_plots, housing_blocks, _ = housing_area.extract(
            housing_doc, HOUSING_BBOX, land_use_of, housing_fills, housing_tree, avoid=[r['geometry'] for r in records])
        for plot in new_plots:
            plot.update(zone=housing_area.ZONE, prefix=housing_area.UID_PREFIX)
            records.append(plot)
        stats['housing_plots'] = len(new_plots)
        stats['housing_blocks'] = len(housing_blocks)
        stats['housing_with_permit'] = sum(1 for p in new_plots if p['permit'])

    to_wgs = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True)

    def transform(x, y):
        return to_wgs.transform(x, y)

    # --- the detail drawing: land use, buildings (اعیان), easements ---
    features, fills, fill_tree, building_polys, easements = [], [], None, [], []
    new_plot_tree = None
    if detail_doc is not None:
        detail = detail_doc.modelspace()
        fills = hatch_fills(detail, detail_doc.layers)
        fill_tree = STRtree([f[0] for f in fills])
        building_polys = list(closed_polygons(detail.query(f'LWPOLYLINE[layer=="{BUILDING_LAYER}"]'), min_area=2))
        for layer, (kind, label) in EASEMENT_LAYERS.items():
            polygons, lines = easement_shapes([e for e in detail if e.dxf.layer == layer])
            for polygon in polygons:
                easements.append(dict(kind=kind, label=label, geometry=polygon))
            for line in lines:
                easements.append(dict(kind=kind, label=label, geometry=line))
        detail_plots = list(closed_polygons(detail.query(f'LWPOLYLINE[layer=="{PLOT_LAYER}"]')))
        new_plot_tree = (STRtree(detail_plots), detail_plots)
        stats['easement_areas'] = sum(1 for e in easements if e['geometry'].geom_type != 'LineString')
        stats['easement_lines'] = sum(1 for e in easements if e['geometry'].geom_type == 'LineString')

    building_tree = STRtree(building_polys) if building_polys else None
    easement_tree = STRtree([e['geometry'] for e in easements]) if easements else None
    land_use_count = collections.Counter()

    parcel_features = []
    for r in records:
        geometry = r['geometry']
        point = geometry.representative_point()
        zone = r.get('zone') or zones['plots'].get(f"{r['block']}-{r['number']}") or zones['blocks'].get(r['block'])
        props = {
            'type': 'parcel', 'kind': r['kind'], 'block': r['block'], 'number': r['number'], 'zone': zone or '',
            'area': round(geometry.area, 1), 'block_source': r['block_source'], 'other_numbers': r['other_numbers'],
            'prefix': r.get('prefix', ''), 'lot_no': r.get('lot_no', ''), 'permit': bool(r.get('permit')),
        }
        if detail_doc is not None or 'land_use' in r:
            use = r['land_use'] if 'land_use' in r else (land_use_of(point, fills, fill_tree) if fills else None)
            props['lu'], props['lu_layer'] = use if use else ('', '')
            land_use_count[props['lu']] += 1
            mine = [building_polys[i] for i in building_tree.query(geometry)
                    if geometry.contains(building_polys[i].representative_point())] if building_tree else []
            props['bld_count'] = len(mine)
            props['bld_area'] = round(sum(b.area for b in mine), 1)
            hits = []
            for i in (easement_tree.query(geometry) if easement_tree else []):
                e = easements[i]
                overlap = geometry.intersection(e['geometry'])
                size = overlap.length if e['geometry'].geom_type == 'LineString' else overlap.area
                if (e['geometry'].geom_type == 'LineString' and size > 0) or size >= MIN_EASEMENT_OVERLAP:
                    hits.append({'k': e['kind'], 'a': round(size, 1),
                                 'line': e['geometry'].geom_type == 'LineString'})
            by_kind = {}
            for h in hits:
                prev = by_kind.get(h['k'])
                if prev is None or h['a'] > prev['a']:
                    by_kind[h['k']] = h
            props['easements'] = sorted(by_kind.values(), key=lambda h: h['k'])
            # survey differences: a plot that is in the 1404 survey but no longer in the 1405 drawing
            if new_plot_tree is not None and not r.get('prefix'):
                tree, polys = new_plot_tree
                twin = any(abs(polys[i].area - geometry.area) <= 0.03 * max(geometry.area, 1) + 0.2
                           and polys[i].centroid.distance(geometry.centroid) < 0.4 for i in tree.query(geometry.buffer(0.3)))
                if r['kind'] == 'drawn' and not twin:
                    props['last_year'] = survey_year
        parcel_features.append({'type': 'Feature', 'properties': props, 'geometry': geometry_json(geometry, transform)})

    uids = parcel_uids(parcel_features)
    counts = collections.Counter((f['properties']['prefix'], f['properties']['block'], f['properties']['number'])
                                 for f in parcel_features if f['properties']['block'] and f['properties']['number'])
    for index, feature in enumerate(parcel_features):
        props = feature['properties']
        props['uid'] = uids[index]
        props['code'] = renewal_code(0, 0, props['number'], props['block'], props['zone'])
        props['duplicate'] = counts.get((props['prefix'], props['block'], props['number']), 0) > 1
        stats['duplicate_codes'] += props['duplicate']
        stats['without_zone'] += not props['zone']
    features.extend(parcel_features)

    plots_per_block = collections.Counter(r['block'] for r in records if r['block'] and not r.get('prefix'))
    housing_per_block = collections.Counter(r['block'] for r in records if r['block'] and r.get('prefix'))
    for number, polygon in sorted(blocks, key=lambda b: (len(b[0]), b[0])):
        features.append({
            'type': 'Feature',
            'properties': {'type': 'block', 'number': number, 'parcels': plots_per_block.get(number, 0),
                           'area': round(polygon.area, 1), 'zone': zones['blocks'].get(number, '')},
            'geometry': geometry_json(polygon, transform),
        })
    for number, polygon in housing_blocks:
        features.append({
            'type': 'Feature',
            'properties': {'type': 'block', 'number': number, 'parcels': housing_per_block.get(number, 0),
                           'area': round(polygon.area, 1), 'zone': '6'},
            'geometry': geometry_json(polygon, transform),
        })

    # buildings (اعیان): footprint and the plot it stands on
    if detail_doc is not None:
        plot_geoms = [r['geometry'] for r in records]
        owner_tree = STRtree(plot_geoms)
        for polygon in building_polys:
            owner = smallest_containing(owner_tree, plot_geoms, polygon.representative_point())
            props = {'type': 'building', 'area': round(polygon.area, 1),
                     'parcel': uids[owner] if owner is not None else ''}
            features.append({'type': 'Feature', 'properties': props, 'geometry': geometry_json(polygon, transform)})
        for e in easements:
            features.append({'type': 'Feature', 'properties': {'type': 'easement', 'kind': e['kind'], 'label': e['label']},
                             'geometry': geometry_json(e['geometry'], transform)})
        stats['buildings'] = len(building_polys)

    # neighbourhoods (حوزه / محله): the blocks of each, with the streets between them closed up
    by_zone = collections.defaultdict(list)
    for number, polygon in blocks:
        if zones['blocks'].get(number):                  # empty blocks belong to a neighbourhood too
            by_zone[zones['blocks'][number]].append(polygon)
    zone_parcels = {zone: sum(plots_per_block.get(n, 0) for n, _ in blocks if zones['blocks'].get(n) == zone) for zone in by_zone}
    if housing_blocks:
        by_zone['6'] = [polygon for _, polygon in housing_blocks]
        zone_parcels['6'] = sum(housing_per_block.values())
    for zone, polygons in sorted(by_zone.items()):
        shape = unary_union(polygons).buffer(14).buffer(-12)
        features.append({'type': 'Feature',
                         'properties': {'type': 'zone', 'number': zone, 'blocks': len(polygons),
                                        'parcels': zone_parcels[zone]},
                         'geometry': geometry_json(shape, transform)})

    # a colour is named after the legend's number of the hatch layer most of its plots come from
    layers_of = collections.defaultdict(collections.Counter)
    for f in parcel_features:
        if f['properties'].get('lu'):
            layers_of[f['properties']['lu']][f['properties'].get('lu_layer', '')] += 1
    land_use_names = {}
    for key, layers in layers_of.items():
        named = collections.Counter()
        for layer, n in layers.items():
            named[land_use_name(layer)] += n
        top = named.most_common(1)[0][0]
        land_use_names[key] = top
    stats['features'] = len(features)
    stats['land_use_classes'] = len(land_use_count)
    collection = {
        'type': 'FeatureCollection', 'features': features,
        'land_use': [{'key': key, 'name': land_use_names.get(key) or LAND_USE_NAMES.get(key, ''), 'plots': count}
                     for key, count in land_use_count.most_common()],
        'years': {'survey': survey_year, 'detail': detail_year},
    }
    return collection, dict(stats)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('dxf', help='the survey drawing (numbers, blocks, plots)')
    parser.add_argument('output')
    parser.add_argument('--detail-dxf', help='the newer drawing with land-use fills, easements and buildings')
    parser.add_argument('--zones', help='JSON written by georef_zones.py: neighbourhood of each block / plot')
    parser.add_argument('--housing-dxf', help='the housing-area plan (neighbourhood 6): subdivision lines, plot labels, permits')
    parser.add_argument('--epsg', type=int, default=32640, help='coordinate system of the drawings (UTM zone 40N)')
    args = parser.parse_args(argv)
    import ezdxf
    sys.stdout.reconfigure(encoding='utf-8')
    zones = json.loads(Path(args.zones).read_text(encoding='utf-8')) if args.zones else None
    detail = ezdxf.readfile(args.detail_dxf) if args.detail_dxf else None
    housing = ezdxf.readfile(args.housing_dxf) if args.housing_dxf else None
    collection, stats = build(ezdxf.readfile(args.dxf), args.epsg, detail_doc=detail, zones=zones, housing_doc=housing)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collection, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for key, value in sorted(stats.items()):
        print(f'{key:28} {value}')
    print('written', out, f'{out.stat().st_size / 1e6:.2f} MB')


if __name__ == '__main__':
    main()
