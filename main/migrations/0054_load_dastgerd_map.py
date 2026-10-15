"""Load the Dastgerd map (blocks and plots) so a deploy needs nothing beyond `migrate`.

Later drawings are loaded with `manage.py load_village_map dastgerd`; archives already entered are kept.
"""
from types import SimpleNamespace

from django.db import migrations


def load(apps, schema_editor):
    from main import geography
    from main.gis import loader
    if not loader.VILLAGES['dastgerd']['file'].exists():
        return
    names = ('VillageMap', 'MapBlock', 'MapParcel', 'CityVillage', 'Province', 'County', 'District')
    models = SimpleNamespace(**{name: apps.get_model('main', name) for name in names})
    loader.load_village_map('dastgerd', models, geography=geography)


class Migration(migrations.Migration):
    dependencies = [('main', '0053_village_gis')]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
