from types import SimpleNamespace

from django.db import migrations

from main.gis import series


def load(apps, schema_editor):
    models = SimpleNamespace(MapParcel=apps.get_model('main', 'MapParcel'))
    for village_map in apps.get_model('main', 'VillageMap').objects.all():
        series.load(village_map, models)


def unload(apps, schema_editor):
    apps.get_model('main', 'MapParcel').objects.exclude(series='').delete()


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0091_parcel_series"),
    ]

    operations = [migrations.RunPython(load, unload)]
