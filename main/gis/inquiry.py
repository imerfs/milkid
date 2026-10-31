"""What a citizen may learn about a plot before buying it (the «استعلام خرید ملک» map).

A lighter reading of the village map than the staff's: for each plot only the number, block, renewal code, area, land use, neighbourhood and a few statuses
(inside the plan, exempt, touched by an easement); never the owner, the permit, payments or locks. It guides a buyer; the official answer is still the
dehyari's inquiry, and every card says so.
"""
import re

from django.core.cache import cache

from main.gis import rules
from main.models import MapParcel, MapZone

DISCLAIMER = 'این اطلاعات راهنما است و جایگزین استعلام رسمی نیست؛ پیش از خرید، پاسخ رسمی را از دهیاری بگیرید.'
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
MAX_RESULTS = 20


def normalise(text):
    return str(text or '').translate(_DIGITS).replace('٫', '.').replace('‌', '').strip()


def _zone_names(village_map):
    return {z.number: (z.name or f'محله‌ی {z.number}') for z in MapZone.objects.filter(village_map=village_map)}


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


def card(parcel, zone_names):
    """One plot for the inquiry card (no private data)."""
    return {
        'id': parcel.pk, 'number': parcel.number, 'block': parcel.block_no, 'code': parcel.renewal_code, 'lot': parcel.lot_no,
        'zone': parcel.zone, 'zone_name': zone_names.get(parcel.zone, ''), 'area': round(parcel.area_m2, 1),
        'land_use': parcel.land_use.name if parcel.land_use_id and parcel.land_use.name else '',
        'in_plan': parcel.in_plan, 'exempt': parcel.exempt, 'estimated': parcel.kind == 'estimated',
        'status': [{'key': k, 'text': t, 'state': s} for k, t, s in statuses(parcel)],
        'notice': DISCLAIMER,
    }


def _round(coords):
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(coords[0], 6), round(coords[1], 6)]
    return [_round(c) for c in coords]


def collection(village_map):
    """GeoJSON of every plot with the short keys the map needs; cached until the drawing or the flags change."""
    flags = (village_map.parcels.filter(in_plan=True).count(), village_map.parcels.filter(exempt=True).count())
    stamp = int(village_map.loaded_at.timestamp()) if village_map.loaded_at else 0
    key = f'inquiry:{village_map.slug}:{stamp}:{flags[0]}-{flags[1]}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    features = []
    for p in village_map.parcels.select_related('land_use').only('id', 'number', 'block_no', 'renewal_code', 'zone', 'area_m2', 'in_plan', 'exempt', 'kind', 'geometry',
                                                               'land_use__name'):
        features.append({'type': 'Feature', 'id': p.pk, 'geometry': {**p.geometry, 'coordinates': _round(p.geometry['coordinates'])},
                         'properties': {'n': p.number, 'b': p.block_no, 'c': p.renewal_code, 'z': p.zone, 'a': round(p.area_m2),
                                        'u': p.land_use.name if p.land_use_id and p.land_use.name else '', 'p': int(p.in_plan), 'x': int(p.exempt), 'e': int(p.kind == 'estimated')}})
    payload = {'type': 'FeatureCollection', 'features': features, 'centre': [village_map.centre_lat, village_map.centre_lng]}
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
    return [card(p, zones) for p in found.distinct().order_by('zone', 'block_no', 'number')[:MAX_RESULTS]]
