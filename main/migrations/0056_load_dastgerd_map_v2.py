"""Superseded by 0058, which loads the map once all the tables and fields it fills exist.

This used to load the second version of the Dastgerd map. It does nothing now: a fresh database gets the map from 0058,
and a database that already ran it keeps its plots, which 0058 updates in place (by uid).
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('main', '0055_gis_layers_zones_locks')]
    operations = [migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop)]
