"""Server panel extras: file manager operations, redirects, page-view stats, code version."""
import io
import tempfile
import zipfile
from pathlib import Path

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from main import serverops
from main.models import DailyPageView, SiteRedirect
from main.tests.helpers import client_for, make_user


class FileActions(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.media = self.base / 'media'
        (self.media / 'a').mkdir(parents=True)
        (self.media / 'a' / 'doc.pdf').write_bytes(b'%PDF-1.4')
        (self.base / 'outside.pdf').write_bytes(b'no')
        self.ov = override_settings(MEDIA_ROOT=str(self.media), PRIVATE_MEDIA_ROOT=str(self.base / 'priv'))
        self.ov.enable()
        self.admin = client_for(make_user('admin'))

    def tearDown(self):
        self.ov.disable()
        self.tmp.cleanup()

    def act(self, op, path, **extra):
        return self.admin.post(reverse('main:admin_server_file_action'), {'op': op, 'root': 'media', 'path': path, **extra})

    def test_mkdir_move_copy_rmdir(self):
        self.act('mkdir', 'a', name='b')
        self.assertTrue((self.media / 'a' / 'b').is_dir())
        self.act('copy', 'a/doc.pdf', dest='a/b/copy.pdf')
        self.act('move', 'a/doc.pdf', dest='renamed.pdf')
        self.assertTrue((self.media / 'a' / 'b' / 'copy.pdf').exists())
        self.assertTrue((self.media / 'renamed.pdf').exists())
        self.assertFalse((self.media / 'a' / 'doc.pdf').exists())
        self.act('rmdir', 'a')                       # not empty: refused
        self.assertTrue((self.media / 'a').exists())

    def test_move_and_copy_cannot_leave_the_root_or_enter_itself(self):
        for op in ('move', 'copy'):
            self.act(op, 'a/doc.pdf', dest='../escaped.pdf')
        self.act('move', 'a', dest='a/inner')
        self.assertFalse((self.base / 'escaped.pdf').exists())
        self.assertTrue((self.media / 'a' / 'doc.pdf').exists())
        self.assertEqual(self.act('zip', '../outside.pdf').status_code, 404)

    def test_zip_then_unzip_round_trip(self):
        self.act('zip', 'a')
        self.assertTrue((self.media / 'a.zip').exists())
        (self.media / 'a.zip').rename(self.media / 'copy.zip')
        self.act('unzip', 'copy.zip')
        self.assertEqual((self.media / 'copy' / 'a' / 'doc.pdf').read_bytes(), b'%PDF-1.4')

    def test_unzip_skips_traversal_and_disallowed_extensions(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('../evil.pdf', 'x')
            zf.writestr('/abs.pdf', 'x')
            zf.writestr('page.html', '<script>')
            zf.writestr('ok/fine.pdf', 'x')
        (self.media / 'up.zip').write_bytes(buf.getvalue())
        self.act('unzip', 'up.zip')
        self.assertFalse((self.media / 'evil.pdf').exists())
        self.assertFalse((self.media / 'up' / 'page.html').exists())
        self.assertTrue((self.media / 'up' / 'ok' / 'fine.pdf').exists())
        self.assertEqual(sorted(p.name for p in (self.media / 'up').rglob('*') if p.is_file()), ['fine.pdf'])

    def test_non_admin_cannot_act(self):
        client = client_for(make_user('dehyari'))
        client.post(reverse('main:admin_server_file_action'), {'op': 'mkdir', 'root': 'media', 'path': '', 'name': 'x'})
        self.assertFalse((self.media / 'x').exists())


class Redirects(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = client_for(make_user('admin'))

    def add(self, old, new, permanent='1'):
        return self.admin.post(reverse('main:admin_server_redirect_add'),
                               {'old_path': old, 'new_path': new, 'permanent': permanent})

    def test_redirect_applies_and_counts(self):
        self.add('/old-page/', '/about/')
        self.add('/tmp-page/', '/contact/', permanent='0')
        r = client_for().get('/old-page/')
        self.assertEqual((r.status_code, r['Location']), (301, '/about/'))
        self.assertEqual(client_for().get('/tmp-page/').status_code, 302)
        self.assertEqual(SiteRedirect.objects.get(old_path='/old-page/').hits, 1)

    def test_admin_area_root_and_bad_targets_are_refused(self):
        for old, new in (('/dashboard/admin/server/', '/'), ('/', '/x/'), ('/a/', '//evil.example'),
                         ('/a/', 'javascript:alert(1)'), ('/a/', 'http://plain.example'), ('no-slash', '/x/')):
            self.add(old, new)
        self.assertFalse(SiteRedirect.objects.exists())

    def test_non_admin_cannot_add(self):
        client_for(make_user('council')).post(reverse('main:admin_server_redirect_add'),
                                              {'old_path': '/x/', 'new_path': '/y/'})
        self.assertFalse(SiteRedirect.objects.exists())


class Stats(TestCase):
    def test_html_page_views_are_counted_but_admin_pages_are_not(self):
        client_for().get('/')
        client_for().get('/')
        admin = client_for(make_user('admin'))
        admin.get(reverse('main:admin_server'))
        self.assertEqual(DailyPageView.objects.get(path='/').views, 2)
        self.assertFalse(DailyPageView.objects.filter(path__startswith='/dashboard/admin/').exists())
        self.assertContains(admin.get(reverse('main:admin_server'), {'tab': 'stats'}), 'بازدید روزانه')

    def test_tabs_render(self):
        admin = client_for(make_user('admin'))
        for tab in ('stats', 'redirects', 'resources'):
            with self.subTest(tab=tab):
                self.assertEqual(admin.get(reverse('main:admin_server'), {'tab': tab}).status_code, 200)


class Version(TestCase):
    def test_reads_branch_and_commit_from_dot_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = Path(tmp) / '.git'
            (git / 'refs' / 'heads').mkdir(parents=True)
            (git / 'HEAD').write_text('ref: refs/heads/main\n')
            (git / 'refs' / 'heads' / 'main').write_text('0123456789abcdef\n')
            with override_settings(BASE_DIR=Path(tmp)):
                self.assertEqual(serverops.code_version(), {'branch': 'main', 'commit': '0123456'})
