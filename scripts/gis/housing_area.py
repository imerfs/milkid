# pylint: disable=import-error  # shapely is only installed where a map is rebuilt (requirements.txt here)
"""The newly planned housing area (نهضت ملی) as neighbourhood 6.

Its drawing has no closed plot outlines: a block is a set of subdivision lines (``tafkik-p``) inside street-edge
lines (``BLOCK`` / ``_Puste``), so the plots are the faces those lines enclose. What the drawing gives each plot:

* ``Number``        the subdivision-plan lot number, 1 to 1008 (unique); kept as ``lot_no``
* ``کد نوسازی``     the renewal-code labels: one big one per block (the block number) and a small one in each plot
                    that has it (the plot's number inside the block)
* ``پروانه``        a hatch over every plot a building permit was issued for
* hatches           the land-use fill, as in the village drawing

Blocks are the groups of plots that touch; a group takes the number of the block label inside it, a group without
one takes the nearest labelled group (up to 150 m).
"""
import collections

ZONE = '6'
UID_PREFIX = '6:'                       # block numbers restart at 1 here, so uids carry the neighbourhood
LOT_LINE_LAYERS = {'tafkik-p', 'BLOCK', '_Puste'}
LABEL_LAYER = 'کد نوسازی'
LOT_NUMBER_LAYER = 'Number'
PERMIT_LAYER = 'پروانه'
BLOCK_LABEL_MIN_HEIGHT = 5              # drawing units: block labels are 10 high, plot labels 3
MIN_LOT_AREA, MAX_LOT_AREA = 20.0, 3000.0
JOIN_TOLERANCE = 0.3                    # plots whose outlines are this close belong to the same block
NEAREST_BLOCK_LIMIT = 150.0
HATCH_SKIP = {PERMIT_LAYER, 'l.building', 'h.building'}


def _shapely():
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, unary_union
    from shapely.strtree import STRtree
    return LineString, Point, polygonize, unary_union, STRtree


def lot_faces(modelspace, bbox):
    """The faces the subdivision and street-edge lines enclose, at plot size."""
    LineString, _, polygonize, unary_union, _ = _shapely()
    x0, y0, x1, y1 = bbox
    lines = []
    for entity in modelspace:
        if entity.dxf.layer not in LOT_LINE_LAYERS:
            continue
        if entity.dxftype() == 'LWPOLYLINE':
            points = [(p[0], p[1]) for p in entity.get_points('xy')]
            if len(points) >= 2 and any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in points):
                lines.append(LineString(points + [points[0]] if entity.closed else points))
        elif entity.dxftype() == 'LINE':
            s, e = entity.dxf.start, entity.dxf.end
            if x0 <= s.x <= x1 and y0 <= s.y <= y1:
                lines.append(LineString([(s.x, s.y), (e.x, e.y)]))
    return [f for f in polygonize(unary_union(lines)) if MIN_LOT_AREA <= f.area <= MAX_LOT_AREA]


def read_labels(modelspace, bbox):
    """(block labels, plot labels, lot numbers), each a list of (Point, text)."""
    _, Point, *_ = _shapely()
    x0, y0, x1, y1 = bbox
    blocks, plots, lots = [], [], []
    for e in modelspace.query('TEXT'):
        p = e.dxf.insert
        text = e.dxf.text.strip()
        if not text or not (x0 <= p.x <= x1 and y0 <= p.y <= y1):
            continue
        point = Point(p.x, p.y)
        if e.dxf.layer == LABEL_LAYER:
            (blocks if e.dxf.height > BLOCK_LABEL_MIN_HEIGHT else plots).append((point, text))
        elif e.dxf.layer == LOT_NUMBER_LAYER:
            lots.append((point, text))
    return blocks, plots, lots


def nearest_inside(polygon, labels):
    """The label inside ``polygon`` closest to its centre, or None."""
    held = [(pt.distance(polygon.centroid), text) for pt, text in labels if polygon.contains(pt)]
    return min(held)[1] if held else None


def group_blocks(lots, block_labels):
    """Group touching plots; name each group after the block label inside it, or the nearest labelled group.

    Returns (group index of every lot, block number of every group or '').
    """
    _, _, _, unary_union, STRtree = _shapely()
    merged = unary_union([lot.buffer(JOIN_TOLERANCE) for lot in lots])
    groups = list(merged.geoms) if merged.geom_type == 'MultiPolygon' else [merged]
    tree = STRtree(groups)
    named = {}
    for point, text in block_labels:
        hits = list(tree.query(point, predicate='within'))
        if hits:
            named.setdefault(hits[0], text)
    names = [named.get(i, '') for i in range(len(groups))]
    for i, group in enumerate(groups):
        if names[i]:
            continue
        near = min(((group.centroid.distance(groups[j].centroid), j) for j in named), default=None)
        if near and near[0] <= NEAREST_BLOCK_LIMIT:
            names[i] = named[near[1]]
    group_of = []
    for lot in lots:
        hits = list(tree.query(lot.representative_point(), predicate='within'))
        group_of.append(hits[0] if hits else None)
    return group_of, names, groups


def extract(doc, bbox, land_use_of, fills, fill_tree, avoid=None):
    """Plots and blocks of the housing area.

    ``land_use_of(point, fills, tree)`` gives (rgb hex, layer) as in build_village_map. ``avoid`` is a list of
    shapely polygons (the village plots already drawn): a face overlapping one is not a new plot.
    Returns (plots, blocks): plots are dicts like build_village_map's records, blocks are (number, polygon).
    """
    _, _, _, unary_union, STRtree = _shapely()
    from ezdxf import path as ezpath
    from shapely.geometry import Polygon
    modelspace = doc.modelspace()
    faces = lot_faces(modelspace, bbox)
    block_labels, plot_labels, lot_numbers = read_labels(modelspace, bbox)

    permits = []
    for hatch in modelspace.query('HATCH'):
        if hatch.dxf.layer != PERMIT_LAYER:
            continue
        try:
            for path in ezpath.from_hatch(hatch):
                points = [(v.x, v.y) for v in path.flattening(0.1)]
                if len(points) >= 3:
                    polygon = Polygon(points).buffer(0)
                    if polygon.geom_type == 'Polygon' and polygon.area > 1:
                        permits.append(polygon)
        except Exception:  # pylint: disable=broad-except
            continue
    permit_tree = STRtree(permits) if permits else None

    keep = []
    avoid_tree = STRtree(avoid) if avoid else None
    for face in faces:
        if avoid_tree is not None and any(face.representative_point().within(avoid[i]) for i in avoid_tree.query(face)):
            continue
        label = nearest_inside(face, plot_labels)
        number = nearest_inside(face, lot_numbers)
        permit = bool(permit_tree is not None and any(face.representative_point().within(permits[i]) for i in permit_tree.query(face)))
        if label or number or permit:                   # a face with none of these is not a plot
            keep.append((face, label or '', number or '', permit))

    lots = [k[0] for k in keep]
    group_of, names, groups = group_blocks(lots, block_labels)
    counts = collections.Counter(names[g] for g in group_of if g is not None and names[g])
    plots = []
    for (face, label, number, permit), g in zip(keep, group_of):
        use = land_use_of(face.representative_point(), fills, fill_tree) if fills else None
        plots.append(dict(kind='drawn', block=names[g] if g is not None else '', number=label, lot_no=number,
                          permit=permit, land_use=use, other_numbers=[], block_source='group', geometry=face))
    by_block = collections.defaultdict(list)
    for (face, *_), g in zip(keep, group_of):
        if g is not None and names[g]:
            by_block[names[g]].append(face)
    blocks = [(number, unary_union([f.buffer(1.0) for f in faces_]).buffer(-0.5)) for number, faces_ in by_block.items()]
    blocks = [(n, b) for n, b in blocks if b.geom_type in ('Polygon', 'MultiPolygon') and not b.is_empty]
    return plots, sorted(blocks, key=lambda b: int(b[0]) if b[0].isdigit() else 0), counts
