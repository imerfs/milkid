"""Run the demo/sample data scripts that live in the project root, in order.

Usage:  python manage.py seed_demo [--only users services ...]
"""
import runpy
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

STEPS = {
    'seed': 'create_seed_data.py',
    'services': 'create_comprehensive_services.py',
    'users': 'create_demo_users.py',
    'properties': 'create_sample_properties.py',
    'geography': 'create_sample_geographic_data.py',
    'messages': 'create_sample_messages.py',
}


class Command(BaseCommand):
    help = 'Populate the database with demo data (idempotent scripts, run in order).'

    def add_arguments(self, parser):
        parser.add_argument('--only', nargs='+', choices=sorted(STEPS), help='run only these steps')

    def handle(self, *args, **options):
        for name in options['only'] or STEPS:
            script = Path(settings.BASE_DIR) / STEPS[name]
            if not script.exists():
                raise CommandError(f'Missing script for step "{name}": {script}')
            self.stdout.write(self.style.MIGRATE_HEADING(f'== {name}: {script.name}'))
            runpy.run_path(str(script), run_name='__main__')
        self.stdout.write(self.style.SUCCESS('Demo data ready.'))
