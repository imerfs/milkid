"""Reload the Dastgerd map with the housing area (neighbourhood 6), the legend's land-use names and the new fields.

Plots are matched by uid, so archives, payments and locks stay attached; the housing plots are new.
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
    dependencies = [('main', '0057_housing_zone_land_building')]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
