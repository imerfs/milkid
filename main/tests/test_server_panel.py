"""Admin server panel: admin-only access, path safety, backups, IP blocking."""
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from main import serverops
from main.models import BlockedIP
from main.tests.helpers import client_for, make_user

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'

GET_PAGES = [('admin_server', []), ('admin_server_files', []), ('admin_server_file_download', []),
             ('admin_server_backup_download', ['db-20260101-000000.sqlite3.gz'])]
POST_ENDPOINTS = [('admin_server_backup', []), ('admin_server_backup_delete', ['db-20260101-000000.sqlite3.gz']),
                  ('admin_server_ip_block', []), ('admin_server_ip_unblock', [1]),
                  ('admin_server_cache_clear', []), ('admin_server_file_delete', []),
                  ('admin_server_file_upload', []), ('admin_server_db_maintain', [])]


class ServerPanelIsAdminOnly(TestCase):
    def assert_refused(self, client, who):
        for name, args in GET_PAGES:
            with self.subTest(who=who, endpoint=name):
                self.assertIn(client.get(reverse(f'main:{name}', args=args)).status_code, (302, 403))
        for name, args in POST_ENDPOINTS:
            with self.subTest(who=who, endpoint=name):
                self.assertIn(client.post(reverse(f'main:{name}', args=args)).status_code, (302, 403))

    def test_anonymous_and_every_other_role_are_refused(self):
        self.assert_refused(client_for(), 'anonymous')
        for role in ('citizen', 'owner', 'dehyari', 'engineer', 'inspector', 'accountant', 'council'):
            self.assert_refused(client_for(make_user(role)), role)

    def test_admin_sees_every_tab(self):
        admin = client_for(make_user('admin'))
        for tab in ('resources', 'database', 'backups', 'logs', 'ips', 'cache'):
            with self.subTest(tab=tab):
                self.assertEqual(admin.get(reverse('main:admin_server'), {'tab': tab}).status_code, 200)
        self.assertEqual(admin.get(reverse('main:admin_server_files')).status_code, 200)


class FilesStayInsideTheirRoot(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / 'media').mkdir()
        (base / 'media' / 'a.txt').write_text('hi')
        (base / 'secret.txt').write_text('no')
        self.ov = override_settings(MEDIA_ROOT=str(base / 'media'), PRIVATE_MEDIA_ROOT=str(base / 'priv'))
        self.ov.enable()
        self.admin = client_for(make_user('admin'))

    def tearDown(self):
        self.ov.disable()
        self.tmp.cleanup()

    def test_traversal_is_refused_for_list_download_and_delete(self):
        for path in ('..', '../secret.txt', '/etc/passwd'):
            with self.subTest(path=path):
                self.assertEqual(self.admin.get(reverse('main:admin_server_files'), {'path': path}).status_code, 404)
                self.assertEqual(self.admin.get(reverse('main:admin_server_file_download'),
                                                {'root': 'media', 'path': path}).status_code, 404)
                self.assertEqual(self.admin.post(reverse('main:admin_server_file_delete'),
                                                 {'root': 'media', 'path': path}).status_code, 404)
        self.assertTrue((Path(self.tmp.name) / 'secret.txt').exists())

    def test_download_and_delete_inside_root(self):
        r = self.admin.get(reverse('main:admin_server_file_download'), {'root': 'media', 'path': 'a.txt'})
        self.assertEqual(b''.join(r.streaming_content), b'hi')
        self.admin.post(reverse('main:admin_server_file_delete'), {'root': 'media', 'path': 'a.txt'})
        self.assertFalse((Path(self.tmp.name) / 'media' / 'a.txt').exists())


    def test_listing_a_subfolder_search_and_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        (Path(self.tmp.name) / 'media' / 'sub').mkdir()
        (Path(self.tmp.name) / 'media' / 'sub' / 'report.pdf').write_bytes(b'%PDF-1.4 x')
        self.assertContains(self.admin.get(reverse('main:admin_server_files'), {'root': 'media', 'path': 'sub'}), 'report.pdf')
        self.assertContains(self.admin.get(reverse('main:admin_server_files'), {'root': 'media', 'q': 'repo'}), 'sub/report.pdf')
        self.admin.post(reverse('main:admin_server_file_upload'), {'root': 'media', 'path': 'sub',
                        'file': SimpleUploadedFile('new.pdf', PDF, content_type='application/pdf')})
        self.assertEqual((Path(self.tmp.name) / 'media' / 'sub' / 'new.pdf').read_bytes(), PDF)

    def test_upload_cannot_escape_the_root(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.admin.post(reverse('main:admin_server_file_upload'), {'root': 'media', 'path': '..',
                                   'file': SimpleUploadedFile('x.pdf', PDF, content_type='application/pdf')})
        self.assertEqual(response.status_code, 404)


class Database(TestCase):
    def test_overview_and_maintenance(self):
        admin = client_for(make_user('admin'))
        self.assertContains(admin.get(reverse('main:admin_server'), {'tab': 'database'}), 'main_blockedip')
        for action in ('check', 'optimize'):
            self.assertEqual(admin.post(reverse('main:admin_server_db_maintain'), {'action': action}).status_code, 302)
        self.assertEqual(admin.post(reverse('main:admin_server_db_maintain'), {'action': 'drop'}).status_code, 404)


class Backups(TestCase):
    def test_only_listed_backup_names_are_served(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BACKUP_DIR=Path(tmp)):
            (Path(tmp) / 'db-20260101-000000.sqlite3.gz').write_bytes(b'x')
            (Path(tmp) / 'notes.txt').write_text('x')
            admin = client_for(make_user('admin'))
            ok = admin.get(reverse('main:admin_server_backup_download', args=['db-20260101-000000.sqlite3.gz']))
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(admin.get(reverse('main:admin_server_backup_download', args=['notes.txt'])).status_code, 404)
            self.assertIsNone(serverops.backup_path('../db-20260101-000000.sqlite3.gz'))

    def test_backup_button_runs_backup_db(self):
        # backup_db itself is covered in test_backup_db; SQLite's backup API blocks inside a test transaction
        with mock.patch('main.views.server_views.call_command') as command:
            client_for(make_user('admin')).post(reverse('main:admin_server_backup'), {'media': '1'})
        self.assertEqual(command.call_args.args[:2], ('backup_db', '--media'))


class IpBlocking(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = client_for(make_user('admin'))

    def test_blocked_ip_gets_403_and_unblock_restores_access(self):
        self.admin.post(reverse('main:admin_server_ip_block'), {'ip': '203.0.113.9', 'reason': 'spam'},
                        REMOTE_ADDR='198.51.100.1')
        self.assertEqual(client_for().get('/', REMOTE_ADDR='203.0.113.9').status_code, 403)
        self.assertNotEqual(client_for().get('/', REMOTE_ADDR='198.51.100.7').status_code, 403)
        self.admin.post(reverse('main:admin_server_ip_unblock', args=[BlockedIP.objects.get().id]))
        self.assertNotEqual(client_for().get('/', REMOTE_ADDR='203.0.113.9').status_code, 403)

    def test_invalid_ip_and_own_ip_are_rejected(self):
        url = reverse('main:admin_server_ip_block')
        self.admin.post(url, {'ip': 'not-an-ip'})
        self.admin.post(url, {'ip': '198.51.100.1'}, REMOTE_ADDR='198.51.100.1')
        self.assertEqual(BlockedIP.objects.count(), 0)
