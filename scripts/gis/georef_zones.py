# pylint: disable=import-error  # numpy/Pillow/pyproj are only installed where a map is rebuilt
"""Read the neighbourhood (محله) of every block off the municipality's coloured picture of the village.

The picture ("راهنمای محلات روستای دستگرد") is not georeferenced, so it is registered on the plots first: its
coloured pixels are matched against the drawn plots by FFT cross-correlation over a range of scales (the scale bar
says 400 m is about 295 px, so the scale lands near 0.73 px/m). The match is checked by how many blocks end up with a
single neighbourhood (99 % for Dastgerd). Every plot then takes the colour under its centre; every block takes the
majority of its plots; a plot that disagrees with its block keeps its own value.

Usage:  python scripts/gis/georef_zones.py picture.jpg main/data/gis/dastgerd.geojson main/data/gis/dastgerd_zones.json

The GeoJSON must come from build_village_map.py (a first run without --zones is fine). The picture's legend colours
are listed in ZONE_COLOURS; change them for another village.
"""
import collections
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer

FRAME = (20, 20, 1400, 1520)                    # the map box inside the picture (pixels)
ZONE_COLOURS = {'1': (247, 142, 56), '2': (250, 250, 100), '3': (161, 194, 152), '4': (40, 145, 200), '5': (232, 20, 26)}
COLOUR_TOLERANCE = 45                           # summed RGB distance
VOTE_OFFSETS = (-3, 0, 3)                       # pixels around a plot's centre that are sampled
NEAREST_BLOCK_LIMIT = 150.0                     # metres: a block with no coloured plot copies a neighbour this close


def classify(picture):
    sub = np.asarray(Image.open(picture).convert('RGB')).astype(int)[FRAME[1]:FRAME[3], FRAME[0]:FRAME[2]]
    names = list(ZONE_COLOURS)
    dist = np.stack([np.abs(sub - np.array(c)).sum(axis=2) for c in ZONE_COLOURS.values()], axis=2)
    index = np.where(dist.min(axis=2) < COLOUR_TOLERANCE, dist.argmin(axis=2) + 1, 0)
    return index, names


def register(label, rings):
    """Best (scale, shift, iou) that lays the plots over the coloured picture; rings are (xs, ys) arrays in metres."""
    colored = (label > 0).astype(np.float32)
    minx = min(r[0].min() for r in rings)
    maxy = max(r[1].max() for r in rings)
    maxx = max(r[0].max() for r in rings)
    miny = min(r[1].min() for r in rings)

    def attempt(scale):
        canvas = Image.new('L', (int((maxx - minx) * scale) + 60, int((maxy - miny) * scale) + 60), 0)
        draw = ImageDraw.Draw(canvas)
        for xs, ys in rings:
            draw.polygon([((x - minx) * scale + 30, (maxy - y) * scale + 30) for x, y in zip(xs, ys)], fill=255)
        plot = (np.asarray(canvas) > 0).astype(np.float32)
        size = (plot.shape[0] + colored.shape[0], plot.shape[1] + colored.shape[1])
        corr = np.fft.irfft2(np.fft.rfft2(colored, size) * np.conj(np.fft.rfft2(plot, size)), size)
        iy, ix = np.unravel_index(corr.argmax(), corr.shape)
        iy = iy - size[0] if iy > size[0] // 2 else iy
        ix = ix - size[1] if ix > size[1] // 2 else ix
        inter = corr.max()
        return float(inter / (colored.sum() + plot.sum() - inter)), int(ix), int(iy)

    results = [(attempt(float(scale)), float(scale)) for scale in np.arange(0.62, 0.90, 0.02)]
    coarse = max(results, key=lambda r: r[0][0])[1]
    results += [(attempt(float(scale)), float(scale)) for scale in np.arange(coarse - 0.02, coarse + 0.0201, 0.004)]
    (iou, sx, sy), scale = max(results, key=lambda r: r[0][0])
    return {'scale': scale, 'iou': iou, 'sx': sx, 'sy': sy, 'minx': float(minx), 'maxy': float(maxy)}


def main(picture, geojson, output):
    sys.stdout.reconfigure(encoding='utf-8')
    label, names = classify(picture)
    height, width = label.shape
    to_utm = Transformer.from_crs('EPSG:4326', 'EPSG:32640', always_xy=True)
    data = json.loads(Path(geojson).read_text(encoding='utf-8'))
    parcels = [f for f in data['features'] if f['properties']['type'] == 'parcel']
    centres = []
    rings = []
    for f in parcels:
        xs, ys = zip(*[to_utm.transform(x, y) for x, y in f['geometry']['coordinates'][0]])
        centres.append((sum(xs) / len(xs), sum(ys) / len(ys)))
        if f['properties']['kind'] == 'drawn':
            rings.append((np.array(xs), np.array(ys)))
    reg = register(label, rings)
    print(f"registration: scale {reg['scale']:.3f} px/m, overlap {reg['iou']:.2f}")

    def zone_at(cx, cy):
        px = (cx - reg['minx']) * reg['scale'] + 30 + reg['sx']
        py = (reg['maxy'] - cy) * reg['scale'] + 30 + reg['sy']
        votes = collections.Counter()
        for dx in VOTE_OFFSETS:
            for dy in VOTE_OFFSETS:
                x, y = int(round(px)) + dx, int(round(py)) + dy
                if 0 <= y < height and 0 <= x < width and label[y, x]:
                    votes[names[int(label[y, x]) - 1]] += 1
        return votes.most_common(1)[0][0] if votes else None

    plot_zone, by_block = {}, collections.defaultdict(collections.Counter)
    for f, (cx, cy) in zip(parcels, centres):
        p = f['properties']
        zone = zone_at(cx, cy)
        if zone and p['kind'] == 'drawn':                 # the picture only shows the drawn plots
            plot_zone[(p['block'], p['number'])] = zone
            if p['block']:
                by_block[p['block']][zone] += 1
    blocks = {b: c.most_common(1)[0][0] for b, c in by_block.items()}
    purity = sum(max(c.values()) for c in by_block.values()) / max(1, sum(sum(c.values()) for c in by_block.values()))
    print(f'blocks with a colour: {len(blocks)}, a block has one neighbourhood for {purity:.1%} of its plots')

    # blocks whose plots are all uncoloured (the newest area): the neighbourhood of the closest coloured block
    block_centre = {}
    for f in data['features']:
        if f['properties']['type'] == 'block':
            xs, ys = zip(*[to_utm.transform(x, y) for x, y in f['geometry']['coordinates'][0]])
            block_centre[f['properties']['number']] = (sum(xs) / len(xs), sum(ys) / len(ys))
    filled = 0
    for number, (cx, cy) in block_centre.items():
        if number in blocks:
            continue
        near = min(((((cx - bx) ** 2 + (cy - by) ** 2) ** 0.5, b) for b, (bx, by) in block_centre.items() if b in blocks),
                   default=None)
        if near and near[0] <= NEAREST_BLOCK_LIMIT:
            blocks[number] = blocks[near[1]]
            filled += 1
    print('blocks given the neighbourhood of a neighbour:', filled)

    plots = {f'{b}-{n}': z for (b, n), z in plot_zone.items() if b and n and blocks.get(b) and blocks[b] != z}
    result = {'blocks': dict(sorted(blocks.items(), key=lambda kv: (len(kv[0]), kv[0]))),
              'plots': plots, 'registration': {'scale': round(reg['scale'], 4), 'overlap': round(reg['iou'], 3)}}
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=0), encoding='utf-8')
    print('plots that differ from their block:', len(plots), '->', output)


if __name__ == '__main__':
    main(*sys.argv[1:4])
