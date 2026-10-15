"""Superseded: the map is now loaded by 0056, after the tables it needs (zones, land use, easements ...) exist.

This used to load the first version of the Dastgerd map. It does nothing now, so a fresh database gets the whole
map from 0056, and a database that already ran it keeps its plots, which 0056 updates in place (by uid).
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('main', '0053_village_gis')]
    operations = [migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop)]
