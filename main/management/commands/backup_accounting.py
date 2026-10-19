"""Write an accounting backup for every municipality that has fiscal years (or one of them), and prune old automatic ones.

Meant for cron / a systemd timer, e.g. ``0 2 * * * cd /opt/milkid && venv/bin/python manage.py backup_accounting``.
"""
from django.core.management.base import BaseCommand, CommandError

from main.accounting import backup
from main.models import FiscalYear, Municipality


class Command(BaseCommand):
    help = 'Create automatic accounting backups (one file per municipality) and keep only the newest ones.'

    def add_arguments(self, parser):
        parser.add_argument('--municipality', type=int, help='only this municipality id')
        parser.add_argument('--keep', type=int, help='how many automatic backups to keep per municipality')

    def handle(self, *args, **options):
        ids = FiscalYear.objects.values_list('municipality_id', flat=True).distinct()
        munis = Municipality.objects.filter(pk__in=ids)
        if options['municipality']:
            munis = munis.filter(pk=options['municipality'])
            if not munis.exists():
                raise CommandError('Municipality not found or it has no accounting data.')
        made = 0
        for muni in munis:
            item = backup.create_for(muni, kind='auto', note='پشتیبان خودکار')
            if options['keep'] is not None:
                backup.prune(muni, options['keep'])
            made += 1
            self.stdout.write(f'{muni.pk}: {item.rows} rows, {item.size} bytes')
        self.stdout.write(f'{made} backup(s) written.')
