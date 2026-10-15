"""Load (or refresh in place) the Dastgerd map: plots, blocks, neighbourhoods, land use, easements, buildings.

Plots are matched by uid, so archives, payments and locks entered earlier stay attached. Later drawings are loaded
with `manage.py load_village_map dastgerd`.
"""
from types import SimpleNamespace

from django.db import migrations


def load(apps, schema_editor):
    from main import geography
    from main.gis import loader
    if not loader.VILLAGES['dastgerd']['file'].exists():
        return
    names = ('VillageMap', 'MapBlock', 'MapParcel', 'MapZone', 'MapEasement', 'MapBuilding', 'LandUseClass',
             'CityVillage', 'Province', 'County', 'District')
    models = SimpleNamespace(**{name: apps.get_model('main', name) for name in names})
    loader.load_village_map('dastgerd', models, geography=geography)


class Migration(migrations.Migration):
    dependencies = [('main', '0055_gis_layers_zones_locks')]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
