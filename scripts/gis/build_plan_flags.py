# pylint: disable=import-error  # shapely and pyproj are installed only where a map is rebuilt (scripts/gis/requirements.txt)
"""Which plots are «داخل طرح» and which are «مستثنیات»: written to main/data/gis/<slug>_flags.json for ``manage.py load_village_map`` to apply.

Input is the layers file made by ``scripts/gis/extract_dxf_layers.py`` from the technical unit's drawing:
  * layer ``mostsniat``  (مستثنیات, drawn in green): a plot is exempt when at least half of it lies inside one of those closed frames;
  * layer ``l.karbari.p`` (the plan's proposed land use): a plot is in the plan when at least 30 % of it lies inside one of its closed areas.
Coordinates are UTM zone 40 N, as in the drawing; the plots are matched in longitude / latitude after conversion.

    python scripts/gis/extract_dxf_layers.py technical.dxf layers.json mostsniat l.karbari.p
    python scripts/gis/build_plan_flags.py layers.json dastgerd
"""
import json
import os
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('MELKID_GIS_DATA') or ROOT / 'main' / 'data' / 'gis')
sys.path.insert(0, str(ROOT))
from main.gis.uids import parcel_uids        # noqa: E402  pylint: disable=wrong-import-position

EXEMPT_LAYER, PLAN_LAYER = 'mostsniat', 'l.karbari.p'
EXEMPT_SHARE, PLAN_SHARE = 0.5, 0.3
TO_LONLAT = Transformer.from_crs('EPSG:32640', 'EPSG:4326', always_xy=True)


def _valid(geometry):
    return geometry if geometry.is_valid else make_valid(geometry)


def closed_areas(entities, layer):
    """The layer's closed polylines (also open ones whose ends meet within half a metre) as lon/lat polygons."""
    out = []
    for item in entities:
        if item['layer'] != layer or item['type'] != 'LWPOLYLINE' or len(item['points']) < 3:
            continue
        pts = item['points']
        closed = item['closed'] or (abs(pts[0][0] - pts[-1][0]) < 0.5 and abs(pts[0][1] - pts[-1][1]) < 0.5)
        if closed:
            polygon = _valid(Polygon([TO_LONLAT.transform(x, y) for x, y in pts]))
            if polygon.area > 0:
                out.append(polygon)
    return out


def flag(parcels, areas, share):
    """uids of the plots with at least ``share`` of their area inside the areas."""
    union = unary_union(areas)
    hits = []
    for uid, geometry in parcels:
        if geometry.area and _valid(geometry).intersection(union).area / geometry.area >= share:
            hits.append(uid)
    return hits


def main(layers_path, slug):
    entities = json.loads(Path(layers_path).read_text(encoding='utf-8'))['entities']
    collection = json.loads((DATA / f'{slug}.geojson').read_text(encoding='utf-8'))
    features = [f for f in collection['features'] if f['properties']['type'] == 'parcel']
    uids = parcel_uids(features)
    parcels = [(f['properties'].get('uid') or uids[i], shape(f['geometry'])) for i, f in enumerate(features)]
    exempt = flag(parcels, closed_areas(entities, EXEMPT_LAYER), EXEMPT_SHARE)
    in_plan = flag(parcels, closed_areas(entities, PLAN_LAYER), PLAN_SHARE)
    result = {'source': f'layers {EXEMPT_LAYER} and {PLAN_LAYER} of the technical unit drawing', 'exempt_share': EXEMPT_SHARE, 'plan_share': PLAN_SHARE,
              'exempt': sorted(exempt), 'in_plan': sorted(in_plan)}
    out = DATA / f'{slug}_flags.json'
    out.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print(f'{len(parcels)} plots: {len(exempt)} exempt, {len(in_plan)} in the plan -> {out}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
