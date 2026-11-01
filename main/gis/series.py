"""Plot-number series: subdivisions whose plots are numbered 1, 2, 3 ... on their own, apart from the village's block-and-plot numbering.

A village may have several (the first is the «بیست هکتاری»). Their plots are ordinary ``MapParcel`` rows with ``series`` set to the key below, so every map and
search sees them; a plain plot number alone is ambiguous between series, so searches take the series name (or a chosen series) with it. The outlines come from
``scripts/gis/build_plot_series.py`` (``<slug>_series_<key>.geojson``) and are loaded with the village map by ``load``.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'gis'      # as in main.gis.loader, which imports this module

SERIES = {
    'dastgerd': {
        'hectare20': {'name': 'بیست هکتاری', 'aliases': ['بیست هکتاری', '20 هکتاری', '20هکتاری', '20 هکتار', 'بیست هکتار'],
                      'file': DATA_DIR / 'dastgerd_series_hectare20.geojson'},
    },
}
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def of_village(slug):
    """The series of a village: key -> spec."""
    return SERIES.get(slug, {})


def name(slug, key):
    return of_village(slug).get(key, {}).get('name', '')


def table(slug, aliases=False):
    """What the pages need: [{key, name}] in registry order (with the words a search may call each by when ``aliases``)."""
    return [{'key': key, 'name': spec['name'], **({'aliases': spec['aliases']} if aliases else {})} for key, spec in of_village(slug).items()]


def split_query(slug, text):
    """Take a series name out of a search text: «بیست هکتاری 12» -> ('hectare20', '12'). No series named -> (None, text)."""
    folded = re.sub(r'\s+', ' ', str(text or '').translate(_DIGITS)).strip()
    for key, spec in of_village(slug).items():
        for alias in sorted(spec['aliases'], key=len, reverse=True):
            pattern = re.compile(rf'(?:^|\s|-){re.escape(alias.translate(_DIGITS))}(?=$|\s|-|\d)', re.IGNORECASE)
            if pattern.search(folded):
                return key, re.sub(r'\s+', ' ', pattern.sub(' ', folded)).strip(' -')
    return None, folded


def _uids(features, key):
    """``s-<key>-<number>``; a number used twice gets ``#2``, ``#3`` ... by size and then position, so a reload keeps them."""
    groups = defaultdict(list)
    for index, feature in enumerate(features):
        groups[feature['properties']['number']].append(index)
    uids = {}
    for number, indexes in groups.items():
        ordered = sorted(indexes, key=lambda i: (-features[i]['properties']['area'], features[i]['geometry']['coordinates'][0][0]))
        for rank, index in enumerate(ordered):
            uids[index] = f's-{key}-{number}' + (f'#{rank + 1}' if rank else '')
    return uids


def has_series(models):
    """False for the historical models of a migration older than the ``series`` column."""
    return any(f.name == 'series' for f in models.MapParcel._meta.get_fields())


def load(village_map, models):
    """Create or update the series plots of the village from their files; a plot gone from a file is deleted unless it has an archive, payments or a lock.
    Returns {key: plots}."""
    done = {}
    for key, spec in of_village(village_map.slug).items():
        if not spec['file'].exists():
            continue
        features = json.loads(spec['file'].read_text(encoding='utf-8'))['features']
        uids = _uids(features, key)
        existing = {p.uid: p for p in models.MapParcel.objects.filter(village_map=village_map, series=key)}
        create, update = [], []
        for index, feature in enumerate(features):
            values = dict(number=feature['properties']['number'], area_m2=feature['properties']['area'], kind='drawn', block_no='', zone='',
                          renewal_code='', series=key, geometry=feature['geometry'])
            row = existing.pop(uids[index], None)
            if row is None:
                create.append(models.MapParcel(village_map=village_map, uid=uids[index], **values))
                continue
            for field, value in values.items():
                setattr(row, field, value)
            update.append(row)
        models.MapParcel.objects.bulk_create(create, batch_size=500)
        if update:
            models.MapParcel.objects.bulk_update(update, ['number', 'area_m2', 'kind', 'block_no', 'zone', 'renewal_code', 'series', 'geometry'], batch_size=500)
        for row in existing.values():
            if not (hasattr(row, 'archive') or row.payments.exists() or row.locks.exists()):
                row.delete()
        done[key] = len(features)
    return done
