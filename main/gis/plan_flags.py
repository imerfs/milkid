"""Apply the «داخل طرح» / «مستثنیات» flags of a village (main/data/gis/<slug>_flags.json, built by scripts/gis/build_plan_flags.py) to its plots."""
import json

from main.gis.loader import DATA_DIR
from main.models import MapParcel, VillageMap


def path_of(slug):
    return DATA_DIR / f'{slug}_flags.json'


def apply(slug):
    """Set ``in_plan`` and ``exempt`` on the village's plots from the flags file; plots not listed get False. Returns the counts, or None without a file."""
    path = path_of(slug)
    if not path.exists():
        return None
    flags = json.loads(path.read_text(encoding='utf-8'))
    village_map = VillageMap.objects.get(slug=slug)
    parcels = MapParcel.objects.filter(village_map=village_map)
    in_plan, exempt = set(flags.get('in_plan', [])), set(flags.get('exempt', []))
    parcels.update(in_plan=False, exempt=False)
    parcels.filter(uid__in=in_plan).update(in_plan=True)
    parcels.filter(uid__in=exempt).update(exempt=True)
    return {'in_plan': parcels.filter(in_plan=True).count(), 'exempt': parcels.filter(exempt=True).count()}
