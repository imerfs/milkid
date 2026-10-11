import gzip
import sqlite3
import tarfile
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from main.models import Province


class BackupDb(TransactionTestCase):   # SQLite backup waits forever on a test-wide open transaction
    def run_backup(self, directory, *args):
        out = StringIO()
        call_command('backup_db', '--dir', str(directory), *args, stdout=out)
        return out.getvalue()

    def test_sqlite_backup_is_a_gzipped_copy_that_restores_with_the_data(self):
        Province.objects.create(name='استان آزمون بکاپ')
        with tempfile.TemporaryDirectory() as tmp:
            self.run_backup(tmp)
            [backup] = Path(tmp).glob('db-*.sqlite3.gz')
            restored = Path(tmp) / 'restored.sqlite3'
            restored.write_bytes(gzip.decompress(backup.read_bytes()))
            db = sqlite3.connect(restored)                              # the restore drill, in miniature
            try:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                names = [r[0] for r in db.execute('SELECT name FROM main_province')]
            finally:
                db.close()                                              # Windows cannot delete an open file
            self.assertIn('استان آزمون بکاپ', names)

    def test_keeps_only_the_newest_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            for day in range(1, 6):
                (Path(tmp) / f'db-2026010{day}-000000.sqlite3.gz').write_bytes(b'old')
            self.run_backup(tmp, '--keep', '3')
            names = sorted(p.name for p in Path(tmp).glob('db-*'))
            self.assertEqual(len(names), 3)
            self.assertNotIn('db-20260101-000000.sqlite3.gz', names)    # oldest are gone
            self.assertNotIn('db-20260102-000000.sqlite3.gz', names)
            self.assertTrue(any(n > 'db-20260105' for n in names))      # the fresh one stays

    def test_media_folder_can_be_included(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as media:
            (Path(media) / 'doc.txt').write_text('سند', encoding='utf-8')
            with override_settings(MEDIA_ROOT=media):
                self.run_backup(tmp, '--media')
            [archive] = Path(tmp).glob('media-*.tar.gz')
            with tarfile.open(archive) as tar:
                self.assertTrue(any(n.endswith('doc.txt') for n in tar.getnames()))

    def test_rejects_a_nonsense_keep_value(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(CommandError):
            self.run_backup(tmp, '--keep', '0')
