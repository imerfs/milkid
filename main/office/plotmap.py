"""A plot and its surroundings from the village map: the four limits (حدود اربعه) and the sheet drawn for form 1.

The limits are worked out from the outlines on the map: each side of the plot is the edges facing that compass
direction; what lies beyond is the neighbouring plot (named by its lot number) or, when no plot is there, a street.
The staff can change every value before the form is made; this only saves the measuring.
"""
from functools import lru_cache

from main.models import MapParcel, VillageMap
from main.office import geo

SIDES = ('north', 'south', 'west', 'east')
SIDE_LABEL = {'north': 'شمالاً', 'south': 'جنوباً', 'west': 'غرباً', 'east': 'شرقاً'}
PROBE_M = 0.8
SHEET_RADIUS_M = 45


@lru_cache(maxsize=4)
def _index(map_id, loaded_key):
    village_map = VillageMap.objects.get(pk=map_id)
    grid = geo.Grid(village_map.centre_lat, village_map.centre_lng)
    rows = []
    for p in MapParcel.objects.filter(village_map=village_map).only('id', 'geometry', 'lot_no', 'number', 'block_no', 'renewal_code', 'kind'):
        try:
            ring = grid.ring(p.geometry['coordinates'][0])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if len(ring) > 3 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) >= 3:
            rows.append({'id': p.pk, 'ring': ring, 'bbox': geo.bbox(ring), 'lot': p.lot_no, 'number': p.number, 'block': p.block_no,
                         'code': p.renewal_code, 'estimated': p.kind == 'estimated'})
    return grid, rows


def index(village_map):
    """(grid, parcels) for a map; rebuilt when the map is reloaded."""
    return _index(village_map.pk, str(village_map.loaded_at))


def _near(rows, box, margin):
    x0, y0, x1, y1 = box
    return [r for r in rows if r['bbox'][2] >= x0 - margin and r['bbox'][0] <= x1 + margin and r['bbox'][3] >= y0 - margin and r['bbox'][1] <= y1 + margin]


def _name(row):
    number = row['lot'] or row['number']
    return f'قطعه {number}' if number else 'ملک'


def limits(village_map, parcel_id=None, ring=None):
    """{'north': {'length': 10.0, 'to': 'معبر'}, ...} for a plot of the map (by id) or for a free outline in local metres."""
    grid, rows = index(village_map)
    own_id = parcel_id
    if ring is None:
        ring = next((r['ring'] for r in rows if r['id'] == parcel_id), None)
    if ring is None:
        return {}
    around = _near(rows, geo.bbox(ring), 3)
    sums = {side: 0.0 for side in SIDES}
    tally = {side: {} for side in SIDES}
    for edge in geo.edges(ring):
        if edge['length'] < 0.4:
            continue
        side = edge['side']
        sums[side] += edge['length']
        mx, my = (edge['a'][0] + edge['b'][0]) / 2, (edge['a'][1] + edge['b'][1]) / 2
        px, py = mx + edge['normal'][0] * PROBE_M, my + edge['normal'][1] * PROBE_M
        hit = next((r for r in around if r['id'] != own_id and geo.contains(r['ring'], px, py)), None)
        label = _name(hit) if hit else 'معبر'
        tally[side][label] = tally[side].get(label, 0.0) + edge['length']
    result = {}
    for side in SIDES:
        if sums[side] <= 0:
            result[side] = {'length': 0.0, 'to': ''}
            continue
        main = max(tally[side].items(), key=lambda kv: kv[1])[0]
        result[side] = {'length': round(sums[side], 2), 'to': main}
    return result


def neighbours(village_map, parcel_id):
    """{'north': [id, ...], ...}: the plots of the map that touch each side of a plot, the longest contact first (streets are left out)."""
    grid, rows = index(village_map)
    ring = next((r['ring'] for r in rows if r['id'] == parcel_id), None)
    if ring is None:
        return {}
    around = _near(rows, geo.bbox(ring), 3)
    contact = {side: {} for side in SIDES}
    for edge in geo.edges(ring):
        if edge['length'] < 0.4:
            continue
        mx, my = (edge['a'][0] + edge['b'][0]) / 2, (edge['a'][1] + edge['b'][1]) / 2
        px, py = mx + edge['normal'][0] * PROBE_M, my + edge['normal'][1] * PROBE_M
        hit = next((r for r in around if r['id'] != parcel_id and geo.contains(r['ring'], px, py)), None)
        if hit:
            contact[edge['side']][hit['id']] = contact[edge['side']].get(hit['id'], 0.0) + edge['length']
    return {side: [i for i, _ in sorted(found.items(), key=lambda kv: -kv[1])] for side, found in contact.items()}


def sheet(village_map, parcel_id=None, ring=None):
    """What the client draws as «نقشه ملک»: the plot, the plots around it and the length of every edge."""
    grid, rows = index(village_map)
    if ring is None:
        ring = next((r['ring'] for r in rows if r['id'] == parcel_id), None)
    if ring is None:
        return None
    box = geo.bbox(ring)
    around = [r for r in _near(rows, box, SHEET_RADIUS_M) if r['id'] != parcel_id]
    cx, cy = geo.centroid(ring)
    return {
        'plot': [[round(x - cx, 2), round(y - cy, 2)] for x, y in ring],
        'neighbours': [{'ring': [[round(x - cx, 2), round(y - cy, 2)] for x, y in r['ring']],
                        'label': r['lot'] or r['number'], 'estimated': r['estimated']} for r in around],
        'edges': [{'a': [round(e['a'][0] - cx, 2), round(e['a'][1] - cy, 2)], 'b': [round(e['b'][0] - cx, 2), round(e['b'][1] - cy, 2)],
                   'length': round(e['length'], 2)} for e in geo.edges(ring) if e['length'] >= 0.4],
        'area': round(geo.area(ring), 2),
    }


def parcel_at(village_map, lat, lng):
    """The plot of the map that contains the point (None when it is in a street or outside)."""
    grid, rows = index(village_map)
    x, y = grid.to_xy(lat, lng)
    for r in rows:
        b = r['bbox']
        if b[0] <= x <= b[2] and b[1] <= y <= b[3] and geo.contains(r['ring'], x, y):
            if not r['estimated']:
                return r
    return None
