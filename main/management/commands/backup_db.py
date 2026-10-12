"""Back up the database (and optionally the uploaded files), then delete the oldest copies.

Usage:  python manage.py backup_db [--dir PATH] [--keep 14] [--media]

SQLite: a consistent copy made with SQLite's own backup API, integrity-checked, then gzipped.
PostgreSQL: a custom-format `pg_dump` (already compressed; restore with `pg_restore`).
A backup only counts once it has been restored somewhere: see docs/operations.md for the drill.
"""
import gzip
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


def prune(directory, pattern, keep):
    """Delete all but the newest ``keep`` files matching ``pattern`` (names carry the timestamp)."""
    for old in sorted(Path(directory).glob(pattern))[:-keep]:
        old.unlink()


class Command(BaseCommand):
    help = 'Back up the database (and uploaded files) and keep only the newest copies.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=str(settings.BACKUP_DIR), help='where to write backups')
        parser.add_argument('--keep', type=int, default=14, help='how many copies to keep (default 14)')
        parser.add_argument('--media', action='store_true', help='also archive the uploaded files')

    def handle(self, *args, **options):
        if options['keep'] < 1:
            raise CommandError('--keep must be at least 1')
        target = Path(options['dir'])
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')

        if connection.vendor == 'sqlite':
            written = self.backup_sqlite(target, stamp)
            pattern = 'db-*.sqlite3.gz'
        elif connection.vendor == 'postgresql':
            written = self.backup_postgres(target, stamp)
            pattern = 'db-*.dump'
        else:
            raise CommandError(f'Unsupported database: {connection.vendor}')
        prune(target, pattern, options['keep'])
        self.stdout.write(self.style.SUCCESS(f'Database: {written} ({written.stat().st_size} bytes)'))

        if options['media']:
            archive = target / f'media-{stamp}.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(settings.MEDIA_ROOT, arcname='media')
            prune(target, 'media-*.tar.gz', options['keep'])
            self.stdout.write(self.style.SUCCESS(f'Media: {archive} ({archive.stat().st_size} bytes)'))

    def backup_sqlite(self, target, stamp):
        connection.ensure_connection()
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'copy.sqlite3'
            dest = sqlite3.connect(copy)
            try:
                connection.connection.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise CommandError('Backup copy failed its integrity check; nothing was written.')
            finally:
                dest.close()
            written = target / f'db-{stamp}.sqlite3.gz'
            with open(copy, 'rb') as src, gzip.open(written, 'wb') as out:
                shutil.copyfileobj(src, out)
        return written

    def backup_postgres(self, target, stamp, db=None):
        db = db or settings.DATABASES['default']
        written = target / f'db-{stamp}.dump'
        env = dict(os.environ, PGPASSWORD=str(db.get('PASSWORD') or ''))
        command = ['pg_dump', '--format=custom', '--no-owner', '-h', str(db['HOST']), '-p', str(db['PORT']),
                   '-U', str(db['USER']), '-f', str(written), str(db['NAME'])]
        try:
            subprocess.run(command, env=env, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            raise CommandError('pg_dump is not installed (apt install postgresql-client).')
        except subprocess.CalledProcessError as error:
            written.unlink(missing_ok=True)
            raise CommandError(f'pg_dump failed: {error.stderr.strip()}')
        return written
