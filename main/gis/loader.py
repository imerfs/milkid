"""Load a village map's GeoJSON (built by scripts/gis/build_village_map.py) into the database.

Safe to run again with a newer drawing: plots are matched by their stable ``uid``, geometry and numbers are
updated in place, and a plot that has an archive or payments is never deleted.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from django.utils import timezone

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'gis'

# The villages that have a map: slug -> how to find them. Dastgerd, Birjand (South Khorasan).
VILLAGES = {
    'dastgerd': {
        'name': 'دستگرد', 'province': 'خراسان جنوبی', 'county': 'بیرجند', 'district': 'مرکزی',
        'file': DATA_DIR / 'dastgerd.geojson',
        'source_note': 'نقشه‌ی برداشت روستای دستگرد (join14040110.dwg)',
    },
}


def _centroid(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def parcel_uids(features):
    """Stable identity per plot: its renewal code, '#2' ... for repeated codes, a position hash if unnumbered."""
    seen = defaultdict(list)
    for index, feature in enumerate(features):
        seen[feature['properties']['code']].append(index)
    uids = {}
    for code, indexes in seen.items():
        if not code:
            for index in indexes:
                lng, lat = _centroid(features[index]['geometry']['coordinates'][0])
                uids[index] = 'u' + hashlib.sha1(f'{lng:.6f},{lat:.6f}'.encode()).hexdigest()[:10]
            continue
        # the biggest keeps the bare code, the rest are numbered by size then position, so a reload keeps them
        ordered = sorted(indexes, key=lambda i: (-features[i]['properties']['area'],
                                                 _centroid(features[i]['geometry']['coordinates'][0])))
        for rank, index in enumerate(ordered):
            uids[index] = code if rank == 0 else f'{code}#{rank + 1}'
    return uids


def load_village_map(slug, models, geography=None, geojson_path=None):
    """Create or update the map ``slug``. ``models`` has VillageMap, MapBlock, MapParcel and CityVillage
    (the real ones, or historical ones inside a migration). Returns a dict of counts."""
    spec = VILLAGES[slug]
    path = Path(geojson_path or spec['file'])
    collection = json.loads(path.read_text(encoding='utf-8'))
    features = collection['features']
    parcels = [f for f in features if f['properties']['type'] == 'parcel']
    blocks = [f for f in features if f['properties']['type'] == 'block']

    ring = [p for f in blocks for p in f['geometry']['coordinates'][0]]
    centre = (sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)) if ring else (0, 0)
    link = geography.resolve(province=spec['province'], county=spec['county'], district=spec['district'],
                             city_village=spec['name'], models=models) if geography else {}
    village_map, _ = models.VillageMap.objects.update_or_create(slug=slug, defaults={
        'name': spec['name'], 'county_name': spec['county'], 'source_note': spec['source_note'],
        'city_village': link.get('city_village_fk'), 'centre_lat': centre[0], 'centre_lng': centre[1],
        'loaded_at': timezone.now(),
    })

    existing = {p.uid: p for p in models.MapParcel.objects.filter(village_map=village_map)}
    uids = parcel_uids(parcels)
    create, update = [], []
    for index, feature in enumerate(parcels):
        props = feature['properties']
        values = dict(block_no=props['block'], number=props['number'], renewal_code=props['code'],
                      kind=props['kind'], area_m2=props['area'], other_numbers=props['other_numbers'],
                      duplicate_code=props['duplicate'], geometry=feature['geometry'])
        uid = uids[index]
        if uid in existing:
            row = existing.pop(uid)
            for key, value in values.items():
                setattr(row, key, value)
            update.append(row)
        else:
            create.append(models.MapParcel(village_map=village_map, uid=uid, **values))
    models.MapParcel.objects.bulk_create(create, batch_size=500)
    if update:
        models.MapParcel.objects.bulk_update(
            update, ['block_no', 'number', 'renewal_code', 'kind', 'area_m2', 'other_numbers', 'duplicate_code',
                     'geometry'], batch_size=500)
    removed = 0
    for uid, row in existing.items():                      # plots that are no longer in the drawing
        if not hasattr(row, 'archive') and not row.payments.exists():
            row.delete()
            removed += 1

    models.MapBlock.objects.filter(village_map=village_map).delete()
    models.MapBlock.objects.bulk_create([
        models.MapBlock(village_map=village_map, number=f['properties']['number'],
                        parcel_count=f['properties']['parcels'], area_m2=f['properties']['area'],
                        geometry=f['geometry']) for f in blocks], batch_size=200)
    return {'parcels_created': len(create), 'parcels_updated': len(update), 'parcels_removed': removed,
            'blocks': len(blocks), 'linked': bool(village_map.city_village_id)}
