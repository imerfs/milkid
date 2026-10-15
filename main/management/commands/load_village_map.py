"""Load or refresh a village's map from its GeoJSON.

Usage:  python manage.py load_village_map dastgerd [--file path/to/new.geojson]

Archives and payments already entered stay attached to their plots (plots are matched by renewal code).
Run it again after loading the geography fixture to link the map to the village in the divisions list.
"""
from django.core.management.base import BaseCommand, CommandError

from main import geography, models
from main.gis import loader


class Command(BaseCommand):
    help = 'Load or refresh a village map (blocks and plots) from its GeoJSON.'

    def add_arguments(self, parser):
        parser.add_argument('slug', choices=sorted(loader.VILLAGES))
        parser.add_argument('--file', help='GeoJSON built by scripts/gis/build_village_map.py')

    def handle(self, *args, **options):
        try:
            result = loader.load_village_map(options['slug'], models, geography=geography,
                                             geojson_path=options['file'])
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        for key, value in result.items():
            self.stdout.write(f'{key:18} {value}')
