"""What a citizen may learn about a plot before buying it (the «استعلام خرید ملک» map).

A lighter reading of the village map than the staff's: for each plot only the number, block, renewal code, area, land use, neighbourhood and a few statuses
(inside the plan, exempt, touched by an easement); never the owner, the permit, payments or locks. It guides a buyer; the official answer is still the
dehyari's inquiry, and every card says so.
"""
import re
import zlib

from django.core.cache import cache

from main.gis import rules
from main.models import MapZone

DISCLAIMER = 'این اطلاعات راهنما است و جایگزین استعلام رسمی نیست؛ پیش از خرید، پاسخ رسمی را از دهیاری بگیرید.'
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
MAX_RESULTS = 20


def normalise(text):
    return str(text or '').translate(_DIGITS).replace('٫', '.').replace('‌', '').strip()


def _zone_names(village_map):
    return {z.number: (z.name or f'محله‌ی {z.number}') for z in MapZone.objects.filter(village_map=village_map)}


def land_use_table(village_map):
    """The village's land-use classes with the names the staff gave their colours; an unnamed colour is still told apart by its number, as on the staff map."""
    return {c.pk: {'id': c.pk, 'color': c.color, 'count': c.plot_count, 'name': c.name or f'کاربری {i} (نام ثبت نشده)'}
            for i, c in enumerate(village_map.land_uses.all(), 1)}


def statuses(parcel):
    """The buyer-facing facts of a plot, as (key, label, state) with state ok / warn / info."""
    rows = [('limit', 'داخل محدوده‌ی روستا', 'ok')]
    rows.append(('plan', 'داخل طرح (کاربری پیشنهادی عمومی)' if parcel.in_plan else 'خارج از طرح', 'warn' if parcel.in_plan else 'ok'))
    rows.append(('exempt', 'جزو مستثنیات' if parcel.exempt else 'جزو مستثنیات نیست', 'info' if parcel.exempt else 'ok'))
    kinds = sorted({hit['k'] for hit in parcel.easement_hits or []})
    if kinds:
        rows.append(('easement', 'تداخل با ' + '، '.join(rules.label(k) for k in kinds), 'warn'))
    if parcel.kind == 'estimated':
        rows.append(('boundary', 'مرز این قطعه در نقشه ترسیم نشده و تقریبی است', 'warn'))
    return rows


def card(parcel, zone_names, land_uses):
    """One plot for the inquiry card (no private data)."""
    return {
        'id': parcel.pk, 'number': parcel.number, 'block': parcel.block_no, 'code': parcel.renewal_code,
        'zone': parcel.zone, 'zone_name': zone_names.get(parcel.zone, ''), 'area': round(parcel.area_m2, 1),
        'land_use': land_uses.get(parcel.land_use_id, {}).get('name', ''), 'land_use_color': land_uses.get(parcel.land_use_id, {}).get('color', ''),
        'in_plan': parcel.in_plan, 'exempt': parcel.exempt, 'estimated': parcel.kind == 'estimated',
        'status': [{'key': k, 'text': t, 'state': s} for k, t, s in statuses(parcel)],
        'notice': DISCLAIMER,
    }


def _round(coords):
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(coords[0], 6), round(coords[1], 6)]
    return [_round(c) for c in coords]


ROADS = ('asphalt', 'gravel', 'jeep')


def _surroundings(village_map):
    """What a street map shows around the plots: street names, the roads and the village limit (no power, water or trees)."""
    from main.gis import data
    streets, roads, limit = [], [], None
    for f in data.static_context(village_map):
        p, g = f['properties'], f['geometry']
        if p.get('g') == 'names' and p.get('name'):
            streets.append({'t': p['name'], 'x': round(g['coordinates'][0], 6), 'y': round(g['coordinates'][1], 6), 'r': p.get('rot', 0), 'h': p.get('h', 3)})
        elif p.get('g') == 'roads' and p.get('k') in ROADS:
            roads.append({'type': 'Feature', 'properties': {'k': p['k']}, 'geometry': {**g, 'coordinates': _round(g['coordinates'])}})
        elif p.get('g') == 'limits' and p.get('k') == 'village' and g['type'] == 'Polygon':
            limit = {'type': 'Feature', 'properties': {}, 'geometry': {**g, 'coordinates': _round(g['coordinates'])}}
    return {'streets': streets, 'roads': roads, 'limit': limit}


def collection(village_map):
    """GeoJSON of every plot with the short keys the map needs (land-use class ``l``), plus the street names, roads and village limit; cached until the drawing or the flags change."""
    flags = (village_map.parcels.filter(in_plan=True).count(), village_map.parcels.filter(exempt=True).count())
    stamp = int(village_map.loaded_at.timestamp()) if village_map.loaded_at else 0
    uses = land_use_table(village_map)
    names = zlib.crc32(repr(sorted((u['id'], u['name'], u['color']) for u in uses.values())).encode())      # a renamed colour changes the answer
    key = f'inquiry:{village_map.slug}:{stamp}:{flags[0]}-{flags[1]}:{names}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    features = []
    for p in village_map.parcels.only('id', 'number', 'block_no', 'renewal_code', 'zone', 'area_m2', 'in_plan', 'exempt', 'kind', 'geometry', 'land_use_id'):
        features.append({'type': 'Feature', 'id': p.pk, 'geometry': {**p.geometry, 'coordinates': _round(p.geometry['coordinates'])},
                         'properties': {'n': p.number, 'b': p.block_no, 'c': p.renewal_code, 'z': p.zone, 'a': round(p.area_m2), 'l': p.land_use_id or 0,
                                        'p': int(p.in_plan), 'x': int(p.exempt), 'e': int(p.kind == 'estimated')}})
    payload = {'type': 'FeatureCollection', 'features': features, 'centre': [village_map.centre_lat, village_map.centre_lng],
               'land_uses': list(uses.values()), **_surroundings(village_map)}
    cache.set(key, payload, 3600)
    return payload


_CODE = re.compile(r'^\d+(-\d+){4}$')


def search(village_map, query):
    """Plots matching a renewal code (0-0-12-69-3), a lot number, plot-block(-neighbourhood) or just a plot number. At most ``MAX_RESULTS``."""
    text = normalise(query)
    if not text:
        return []
    text = re.sub(r'[\s/_.\\]+', '-', text)
    parcels = village_map.parcels.select_related('land_use')
    if _CODE.match(text):
        found = parcels.filter(renewal_code=text)
    else:
        parts = [p for p in text.split('-') if p]
        if not parts or not all(p.isdigit() for p in parts) or len(parts) > 3:
            return []
        if len(parts) == 1:
            found = parcels.filter(number=parts[0]) | parcels.filter(lot_no=parts[0])
        elif len(parts) == 2:                                       # plot-block, or block-plot
            found = parcels.filter(number=parts[0], block_no=parts[1]) | parcels.filter(number=parts[1], block_no=parts[0])
        else:                                                      # plot-block-neighbourhood
            found = parcels.filter(number=parts[0], block_no=parts[1], zone=parts[2])
    zones = _zone_names(village_map)
    uses = land_use_table(village_map)
    return [card(p, zones, uses) for p in found.distinct().order_by('zone', 'block_no', 'number')[:MAX_RESULTS]]
