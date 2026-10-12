"""Finding geography rows from the place names stored as text on profiles, municipalities and ads."""
import re

LEVELS = ('province', 'county', 'district', 'city_village')
LINKS = ('province_fk', 'county_fk', 'district_fk', 'city_village_fk')


def norm(name):
    """Compare names regardless of Arabic letters, half-spaces and spaces."""
    return re.sub(r'\s+', '', (name or '').replace('ي', 'ی').replace('ك', 'ک').replace('‌', ''))


def resolve(province='', county='', district='', city_village='', models=None):
    """Return {province_fk, county_fk, district_fk, city_village_fk} for the names given (None where not found).

    Each level is looked for inside the level above, so a village that shares its name with another county's
    village is never confused. The district may be empty: the settlement is then looked for in the whole county.
    ``models`` lets a migration pass historical models.
    """
    if models is None:
        from main import models as models
    found = dict.fromkeys(LINKS)

    prov = _by_name(models.Province.objects.all(), province)
    found['province_fk'] = prov
    cnty = _by_name(models.County.objects.filter(province=prov), county) if prov else None
    found['county_fk'] = cnty
    dist = _by_name(models.District.objects.filter(county=cnty), district) if cnty and district else None
    found['district_fk'] = dist
    if dist:
        settlements = models.CityVillage.objects.filter(district=dist)
    elif cnty:
        settlements = models.CityVillage.objects.filter(district__county=cnty)
    else:
        settlements = None
    if settlements is not None and city_village:
        found['city_village_fk'] = _by_name(settlements, city_village)
    return found


def _by_name(queryset, name):
    wanted = norm(name)
    if not wanted:
        return None
    for row in queryset:
        if norm(row.name) == wanted:
            return row
    return None


def backfill(apps):
    """Fill the links of rows written before the links existed (used by the migration)."""
    models = type('M', (), {n: apps.get_model('main', n) for n in ('Province', 'County', 'District', 'CityVillage')})
    cache = {}
    for model_name in ('UserProfile', 'Municipality', 'PropertyAdvertisement'):
        model = apps.get_model('main', model_name)
        batch = []
        for row in model.objects.exclude(province__isnull=True).exclude(province='').iterator(chunk_size=500):
            key = tuple(getattr(row, n) or '' for n in LEVELS)
            if key not in cache:
                cache[key] = resolve(*key, models=models)
            for name, value in cache[key].items():
                setattr(row, name, value)
            batch.append(row)
            if len(batch) >= 500:
                model.objects.bulk_update(batch, LINKS)
                batch = []
        if batch:
            model.objects.bulk_update(batch, LINKS)
