"""What the map page downloads: static geometry (cached per load of the drawing) plus the live flags per plot."""
import json
from datetime import date

from main.models import (MapBlock, MapBuilding, MapEasement, MapParcel, MapZone, ParcelArchive, ParcelFeePayment,
                         ParcelLock)

_static = {}


def _cached(key, loaded_at, build):
    """Parse the JSON geometry once per (map, load of the drawing); the cache dies with the process."""
    hit = _static.get(key)
    if hit and hit[0] == loaded_at:
        return hit[1]
    value = build()
    _static[key] = (loaded_at, value)
    return value


def _jalali_year(value):
    import jdatetime
    if isinstance(value, date):
        return jdatetime.date.fromgregorian(date=value if not hasattr(value, 'date') else value.date()).year
    return None


def static_parcels(village_map):
    def build():
        rows = []
        for p in village_map.parcels.only('id', 'renewal_code', 'block_no', 'number', 'zone', 'kind', 'area_m2',
                                          'land_use_id', 'building_area_m2', 'easement_hits', 'first_year',
                                          'last_year', 'duplicate_code', 'lot_no', 'permit_in_drawing', 'geometry'):
            rows.append({
                'type': 'Feature',
                'properties': {'id': p.pk, 'code': p.renewal_code, 'b': p.block_no, 'n': p.number, 'z': p.zone,
                               'e': p.kind == 'estimated', 'a': round(p.area_m2), 'lu': p.land_use_id or 0,
                               'ba': round(p.building_area_m2), 'h': sorted({h['k'] for h in p.easement_hits}),
                               'fy': p.first_year, 'ly': p.last_year, 'd': p.duplicate_code, 'lt': p.lot_no,
                               'pm': p.permit_in_drawing},
                'geometry': p.geometry,
            })
        return rows
    return _cached((village_map.slug, 'parcels'), village_map.loaded_at, build)


def static_blocks(village_map):
    return _cached((village_map.slug, 'blocks'), village_map.loaded_at, lambda: [
        {'type': 'Feature', 'properties': {'n': b.number, 'c': b.parcel_count, 'z': b.zone}, 'geometry': b.geometry}
        for b in MapBlock.objects.filter(village_map=village_map)])


def static_zones(village_map):
    return _cached((village_map.slug, 'zones'), village_map.loaded_at, lambda: [
        {'type': 'Feature', 'properties': {'n': z.number, 'name': z.name or f'محله {z.number}', 'c': z.parcel_count},
         'geometry': z.geometry} for z in MapZone.objects.filter(village_map=village_map)])


def static_buildings(village_map):
    return _cached((village_map.slug, 'buildings'), village_map.loaded_at, lambda: [
        {'type': 'Feature', 'properties': {'p': b.parcel_id or 0, 'a': round(b.area_m2), 'by': b.built_year},
         'geometry': b.geometry} for b in MapBuilding.objects.filter(village_map=village_map)])


def static_easements(village_map):
    return _cached((village_map.slug, 'easements'), village_map.loaded_at, lambda: [
        {'type': 'Feature', 'properties': {'k': e.kind, 'label': e.label}, 'geometry': e.geometry}
        for e in MapEasement.objects.filter(village_map=village_map)])


def live_flags(village_map):
    """Per plot, what changes while people work: archive filled in (and its permit year), payment years, locks."""
    flags = {}

    def entry(parcel_id):
        return flags.setdefault(parcel_id, {'f': 0, 'py': None, 'pay': [], 'lk': []})

    for parcel_id, permit_date, *rest in ParcelArchive.objects.filter(parcel__village_map=village_map).values_list(
            'parcel_id', 'permit_date', 'owner_name', 'permit_number'):
        filled = bool(permit_date or rest[0] or rest[1])
        row = entry(parcel_id)
        row['f'] = 1 if filled else 0
        row['py'] = _jalali_year(permit_date)
    for parcel_id, paid_on, year in ParcelFeePayment.objects.filter(parcel__village_map=village_map).values_list(
            'parcel_id', 'paid_on', 'fiscal_year'):
        entry(parcel_id)['pay'].append(_jalali_year(paid_on) or year)
    for parcel_id, locked_at, unlocked_at in ParcelLock.objects.filter(parcel__village_map=village_map).values_list(
            'parcel_id', 'locked_at', 'unlocked_at'):
        entry(parcel_id)['lk'].append([_jalali_year(locked_at), _jalali_year(unlocked_at) or 0])
    return flags


def map_collection(village_map):
    flags = live_flags(village_map)
    parcels = []
    for feature in static_parcels(village_map):
        props = dict(feature['properties'])
        props.update(flags.get(props['id'], {'f': 0, 'py': None, 'pay': [], 'lk': []}))
        parcels.append({'type': 'Feature', 'properties': props, 'geometry': feature['geometry']})
    return {
        'parcels': {'type': 'FeatureCollection', 'features': parcels},
        'blocks': {'type': 'FeatureCollection', 'features': static_blocks(village_map)},
        'zones': {'type': 'FeatureCollection', 'features': static_zones(village_map)},
        'land_uses': [{'id': c.pk, 'color': c.color, 'name': c.name or '', 'count': c.plot_count}
                      for c in village_map.land_uses.all()],
        'centre': [village_map.centre_lat, village_map.centre_lng],
    }


def current_year():
    """The current Jalali year (the timeline runs up to it)."""
    import jdatetime
    return jdatetime.date.today().year


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
