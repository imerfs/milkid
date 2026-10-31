"""Map tiles kept on the server's own disk.

The site runs in Iran, where Esri and Google refuse requests, and a visitor's browser would hit the same wall. The village's satellite picture is
therefore downloaded once (scripts/gis/cache_tiles.py) into ``main/data/gis/tiles/<slug>/<layer>/<z>/<x>/<y>.jpg`` and served by Django from there.
"""
import copy

from django.conf import settings
from django.urls import reverse

from main.gis.loader import DATA_DIR

LAYERS = ('satellite',)
ATTRIBUTION = 'Imagery © Esri, Maxar, Earthstar Geographics'


def root(slug, layer):
    return DATA_DIR / 'tiles' / slug / layer


def tile_path(slug, layer, z, x, y):
    """The file of one tile, or None when the request names something that is not a tile of ours."""
    if layer not in LAYERS or not 0 <= z <= 22 or x < 0 or y < 0:
        return None
    path = root(slug, layer) / str(z) / str(x) / f'{y}.jpg'
    return path if path.is_file() else None


def available(slug, layer='satellite'):
    base = root(slug, layer)
    return base.is_dir() and any(base.iterdir())


def url_template(slug, layer='satellite'):
    return reverse('main:gis_tile', args=[slug, layer, 0, 0, 0]).replace('/0/0/0.jpg', '/{z}/{x}/{y}.jpg')


def basemaps(slug):
    """The base-map list for one village: its stored satellite picture replaces the foreign one, which an Iranian visitor cannot load."""
    maps = copy.deepcopy(settings.GIS_BASEMAPS)
    if not available(slug):
        return maps
    for entry in maps:
        if entry['id'] == 'satellite' and not getattr(settings, 'GIS_SATELLITE_TILE_URL', ''):
            entry.update(url=url_template(slug), label='ماهواره‌ای (تصویر ذخیره‌شده روی سرور)', wayback=False, nativeZoom=18,
                         attribution=ATTRIBUTION)
    return maps


def local_satellite(slug):
    """The stored satellite layer as a base-map entry for the inquiry map, or None."""
    return next((m for m in basemaps(slug) if m['id'] == 'satellite' and not m['url'].startswith('http')), None)

