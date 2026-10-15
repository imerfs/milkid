"""Load a village map's GeoJSON (built by scripts/gis/build_village_map.py) into the database.

Safe to run again with a newer drawing: plots are matched by their stable ``uid``, geometry and numbers are
updated in place, and a plot that has an archive, payments or a lock is never deleted. Names an administrator gave
to land-use classes and neighbourhoods are kept.
"""
import json
from pathlib import Path

from django.utils import timezone

from main.gis.uids import parcel_uids, renewal_code

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'gis'

# The villages that have a map: slug -> how to find them. Dastgerd, Birjand (South Khorasan).
VILLAGES = {
    'dastgerd': {
        'name': 'دستگرد', 'province': 'خراسان جنوبی', 'county': 'بیرجند', 'district': 'مرکزی',
        'file': DATA_DIR / 'dastgerd.geojson',
        'source_note': 'نقشه‌ی برداشت دستگرد (join14040110)، نقشه‌ی ۱۴۰۵ (Pish-Dastgerd) و طرح نهضت ملی (محله‌ی ۶)',
    },
}

PARCEL_FIELDS = ['block_no', 'number', 'renewal_code', 'kind', 'area_m2', 'other_numbers', 'duplicate_code', 'zone',
                 'land_use', 'building_area_m2', 'building_count', 'easement_hits', 'first_year', 'last_year',
                 'lot_no', 'permit_in_drawing', 'geometry']


def outer_points(geometry):
    """The points of the outer ring(s) of a Polygon or MultiPolygon."""
    if geometry['type'] == 'MultiPolygon':
        return [point for polygon in geometry['coordinates'] for point in polygon[0]]
    return geometry['coordinates'][0]


def _has_other_links(parcel):
    return hasattr(parcel, 'archive') or parcel.payments.exists() or parcel.locks.exists()


def load_village_map(slug, models, geography=None, geojson_path=None):
    """Create or update the map ``slug``. ``models`` has VillageMap, MapBlock, MapParcel, MapZone, MapEasement,
    MapBuilding, LandUseClass and CityVillage (the real ones, or historical ones inside a migration).
    Returns a dict of counts."""
    spec = VILLAGES[slug]
    path = Path(geojson_path or spec['file'])
    collection = json.loads(path.read_text(encoding='utf-8'))
    features = collection['features']
    by_type = {name: [f for f in features if f['properties']['type'] == name]
               for name in ('parcel', 'block', 'zone', 'easement', 'building')}

    ring = [p for f in by_type['block'] for p in outer_points(f['geometry'])]
    centre = (sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)) if ring else (0, 0)
    link = geography.resolve(province=spec['province'], county=spec['county'], district=spec['district'],
                             city_village=spec['name'], models=models) if geography else {}
    village_map, _ = models.VillageMap.objects.update_or_create(slug=slug, defaults={
        'name': spec['name'], 'county_name': spec['county'], 'source_note': spec['source_note'],
        'city_village': link.get('city_village_fk'), 'centre_lat': centre[0], 'centre_lng': centre[1],
        'loaded_at': timezone.now(),
    })

    # land-use classes: new ones from the drawing; a name someone typed is never overwritten
    classes = {}
    for item in collection.get('land_use', []):
        if not item['key']:
            continue
        row, created = models.LandUseClass.objects.get_or_create(
            village_map=village_map, key=item['key'], defaults={'name': item['name'], 'plot_count': item['plots']})
        if not created:
            row.plot_count = item['plots']
            if not row.name and item['name']:
                row.name = item['name']
            row.save()
        classes[item['key']] = row

    existing = {p.uid: p for p in models.MapParcel.objects.filter(village_map=village_map)}
    uids = parcel_uids(by_type['parcel'])
    uid_of_index = {}
    create, update = [], []
    for index, feature in enumerate(by_type['parcel']):
        props = feature['properties']
        uid = props.get('uid') or uids[index]
        uid_of_index[uid] = True
        row = existing.pop(uid, None)
        guild, apartment = (row.guild_no, row.apartment_no) if row else (0, 0)
        values = dict(block_no=props['block'], number=props['number'], kind=props['kind'], area_m2=props['area'],
                      other_numbers=props['other_numbers'], duplicate_code=props['duplicate'], zone=props['zone'],
                      renewal_code=renewal_code(guild, apartment, props['number'], props['block'], props['zone']),
                      land_use=classes.get(props.get('lu')), building_area_m2=props.get('bld_area', 0),
                      building_count=props.get('bld_count', 0), easement_hits=props.get('easements', []),
                      first_year=props.get('first_year'), last_year=props.get('last_year'),
                      lot_no=props.get('lot_no', ''), permit_in_drawing=bool(props.get('permit')),
                      geometry=feature['geometry'])
        if row is not None:
            for key, value in values.items():
                setattr(row, key, value)
            update.append(row)
        else:
            create.append(models.MapParcel(village_map=village_map, uid=uid, **values))
    models.MapParcel.objects.bulk_create(create, batch_size=500)
    if update:
        models.MapParcel.objects.bulk_update(update, PARCEL_FIELDS, batch_size=500)
    removed = 0
    for row in existing.values():                      # plots that are no longer in the drawing
        if not _has_other_links(row):
            row.delete()
            removed += 1

    models.MapBlock.objects.filter(village_map=village_map).delete()
    models.MapBlock.objects.bulk_create([
        models.MapBlock(village_map=village_map, number=f['properties']['number'], zone=f['properties'].get('zone', ''),
                        parcel_count=f['properties']['parcels'], area_m2=f['properties']['area'],
                        geometry=f['geometry']) for f in by_type['block']], batch_size=200)

    names = dict(models.MapZone.objects.filter(village_map=village_map).values_list('number', 'name'))
    models.MapZone.objects.filter(village_map=village_map).delete()
    models.MapZone.objects.bulk_create([
        models.MapZone(village_map=village_map, number=f['properties']['number'], name=names.get(f['properties']['number'], ''),
                       block_count=f['properties']['blocks'], parcel_count=f['properties']['parcels'],
                       geometry=f['geometry']) for f in by_type['zone']])

    models.MapEasement.objects.filter(village_map=village_map).delete()
    models.MapEasement.objects.bulk_create([
        models.MapEasement(village_map=village_map, kind=f['properties']['kind'], label=f['properties']['label'],
                           geometry=f['geometry']) for f in by_type['easement']], batch_size=200)

    parcel_ids = dict(models.MapParcel.objects.filter(village_map=village_map).values_list('uid', 'pk'))
    models.MapBuilding.objects.filter(village_map=village_map).delete()
    models.MapBuilding.objects.bulk_create([
        models.MapBuilding(village_map=village_map, parcel_id=parcel_ids.get(f['properties']['parcel']),
                           area_m2=f['properties']['area'], geometry=f['geometry']) for f in by_type['building']],
        batch_size=500)
    return {'parcels_created': len(create), 'parcels_updated': len(update), 'parcels_removed': removed,
            'blocks': len(by_type['block']), 'zones': len(by_type['zone']), 'easements': len(by_type['easement']),
            'buildings': len(by_type['building']), 'land_use_classes': len(classes),
            'linked': bool(village_map.city_village_id)}
