# pylint: disable=import-error  # shapely, pyproj and ezdxf are installed only where a map is rebuilt (requirements.txt)
"""Bring the building footprints (اعیان) of a village map up to date with a newer detail drawing.

Plots, blocks, neighbourhoods and easements stay as they are in the GeoJSON (the plot numbers come from the survey,
which the newer drawing does not carry). Every closed polyline of the drawing's ``l.building`` layer becomes a
building; it belongs to the plot that holds most of its area (ties and buildings outside every plot keep no plot).
Each plot's building count and area are recomputed from them. Prints what changed against the file it replaces.

Usage:  python scripts/gis/refresh_buildings.py detail.dxf main/data/gis/dastgerd.geojson
"""
import argparse
import json
import sys
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.strtree import STRtree

BUILDING_LAYER = 'l.building'
MIN_AREA = 2.0


def ring_utm(geometry, to_utm):
    ring = geometry['coordinates'][0] if geometry['type'] == 'Polygon' else geometry['coordinates'][0][0]
    return Polygon([to_utm.transform(x, y) for x, y in ring]).buffer(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dxf')
    parser.add_argument('geojson')
    args = parser.parse_args()
    path = Path(args.geojson)
    collection = json.loads(path.read_text(encoding='utf-8'))
    to_utm = Transformer.from_crs('EPSG:4326', 'EPSG:32640', always_xy=True)
    to_lonlat = Transformer.from_crs('EPSG:32640', 'EPSG:4326', always_xy=True)

    parcels = [(f['properties'].get('uid'), ring_utm(f['geometry'], to_utm)) for f in collection['features']
               if f['properties']['type'] == 'parcel']
    tree = STRtree([p for _, p in parcels])

    footprints = []
    for e in ezdxf.readfile(args.dxf).modelspace():
        if e.dxftype() != 'LWPOLYLINE' or not e.closed or e.dxf.layer != BUILDING_LAYER:
            continue
        points = [(p.x, p.y) for p in ezpath.make_path(e).flattening(0.3)]
        if len(points) >= 3:
            fixed = Polygon(points).buffer(0)             # a self-touching outline splits into its parts
            for part in getattr(fixed, 'geoms', [fixed]):
                if part.geom_type == 'Polygon' and part.area >= MIN_AREA:
                    footprints.append(part)

    buildings, per_plot = [], {}
    for poly in footprints:
        best, best_overlap = None, 0.0
        for index in tree.query(poly):
            overlap = poly.intersection(parcels[index][1]).area
            if overlap > best_overlap:
                best, best_overlap = parcels[index][0], overlap
        owner = best if best_overlap >= poly.area * 0.5 else None
        coords = [[round(x, 7), round(y, 7)] for x, y in (to_lonlat.transform(px, py) for px, py in poly.exterior.coords)]
        buildings.append({'type': 'Feature', 'properties': {'type': 'building', 'area': round(poly.area, 1), 'parcel': owner},
                          'geometry': {'type': 'Polygon', 'coordinates': [coords]}})
        if owner:
            count, area = per_plot.get(owner, (0, 0.0))
            per_plot[owner] = (count + 1, area + poly.area)

    old_buildings = [f for f in collection['features'] if f['properties']['type'] == 'building']
    rest = [f for f in collection['features'] if f['properties']['type'] != 'building']
    for f in rest:
        if f['properties']['type'] == 'parcel':
            count, area = per_plot.get(f['properties'].get('uid'), (0, 0.0))
            f['properties']['bld_count'], f['properties']['bld_area'] = count, round(area, 1)
    collection['features'] = rest + buildings
    path.write_text(json.dumps(collection, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'buildings {len(old_buildings)} -> {len(buildings)} '
          f'({sum(1 for b in buildings if b["properties"]["parcel"] is None)} on no plot); '
          f'plots with a building: {len(per_plot)}')


if __name__ == '__main__':
    sys.exit(main())
