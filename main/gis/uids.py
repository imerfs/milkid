"""Plot identity and renewal code, shared by the loader and the build scripts."""
import hashlib
from collections import defaultdict


def _centroid(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def parcel_uids(features):
    """uid per feature index: ``block-plot``, ``block-plot#2`` for repeats, a position hash if unnumbered.

    ``features`` are the plots' GeoJSON features with ``properties.block``, ``number`` and ``area``.
    """
    seen = defaultdict(list)
    for index, feature in enumerate(features):
        props = feature['properties']
        key = f"{props['block']}-{props['number']}" if props['block'] and props['number'] else ''
        seen[key].append(index)
    uids = {}
    for key, indexes in seen.items():
        if not key:
            for index in indexes:
                lng, lat = _centroid(features[index]['geometry']['coordinates'][0])
                uids[index] = 'u' + hashlib.sha1(f'{lng:.6f},{lat:.6f}'.encode()).hexdigest()[:10]
            continue
        # the biggest keeps the bare key, the rest are numbered by size then position, so a reload keeps them
        ordered = sorted(indexes, key=lambda i: (-features[i]['properties']['area'],
                                                 _centroid(features[i]['geometry']['coordinates'][0])))
        for rank, index in enumerate(ordered):
            uids[index] = key if rank == 0 else f'{key}#{rank + 1}'
    return uids


def renewal_code(guild, apartment, plot, block, zone):
    """The renewal code (کد نوسازی): صنف - آپارتمان - ملک - بلوک - محله.

    A plot (the land itself) has no guild or apartment unit, so those are 0; units get their own numbers later.
    Without a plot number, block or neighbourhood there is no code.
    """
    if not (plot and block and zone):
        return ''
    return f'{guild}-{apartment}-{plot}-{block}-{zone}'
