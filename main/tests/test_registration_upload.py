"""Registration: the Jalali founding date is picked from selects; the governor's decree is stored and admin-only."""
import shutil
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import Municipality
from main.tests.helpers import client_for, make_user
from main.tests.test_municipality_account import place, registration_data

PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n'


class RegistrationUpload(TestCase):
    def setUp(self):
        cache.clear()  # registration is throttled per IP; tests share the cache
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.settings = override_settings(PRIVATE_MEDIA_ROOT=self.root, MAX_FILE_SIZE=1024)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.p, self.c, self.d = place()

    def register(self, **over):
        data = registration_data(self.p, self.c, self.d, **over)
        if 'establishment_date' in over and over['establishment_date'] is None:
            del data['establishment_date']
        return self.client.post(reverse('main:register_municipality'), data)

    def test_decree_is_really_stored(self):
        self.assertEqual(self.register().status_code, 302)
        town = Municipality.objects.get()
        self.assertTrue(town.governor_decree)
        with town.governor_decree.open('rb') as f:
            self.assertEqual(f.read(), PDF)

    def test_bad_decree_is_rejected(self):
        for name, body in (('decree.exe', b'MZ\x90\x00'), ('decree.pdf', b'MZ\x90\x00' + b'0' * 50),
                           ('decree.pdf', PDF + b'0' * 2000)):
            response = self.register(governor_decree=SimpleUploadedFile(name, body))
            self.assertIn(response.status_code, (200, 400), name)   # 400: the global upload guard stopped it first
            if response.status_code == 200:
                self.assertIn('governor_decree', response.context['form'].errors, name)
        self.assertEqual(Municipality.objects.count(), 0)

    def test_jalali_selects_become_the_gregorian_date(self):
        response = self.register(establishment_date=None, establishment_date_year='1399',
                                 establishment_date_month='10', establishment_date_day='12')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(Municipality.objects.get().establishment_date), '2021-01-01')

    def test_impossible_jalali_date_is_rejected(self):
        response = self.register(establishment_date=None, establishment_date_year='1399',
                                 establishment_date_month='12', establishment_date_day='31')   # 1399 is not a leap year
        self.assertEqual(response.status_code, 200)
        self.assertIn('establishment_date', response.context['form'].errors)

    def test_form_renders_year_month_day_selects(self):
        html = self.client.get(reverse('main:register_municipality')).content.decode()
        for suffix in ('year', 'month', 'day'):
            self.assertIn(f'name="establishment_date_{suffix}"', html)


class DecreeDownload(TestCase):
    def setUp(self):
        cache.clear()
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        override = override_settings(PRIVATE_MEDIA_ROOT=root)
        override.enable()
        self.addCleanup(override.disable)
        p, c, d = place()
        self.client.post(reverse('main:register_municipality'), registration_data(p, c, d))
        self.town = Municipality.objects.get()
        self.url = reverse('main:municipality_decree', args=[self.town.id])

    def test_admin_downloads_the_file(self):
        response = client_for(make_user('admin')).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), PDF)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_others_cannot(self):
        self.assertNotEqual(client_for().get(self.url).status_code, 200)
        for role in ('citizen', 'dehyari', 'accountant'):
            self.assertNotEqual(client_for(make_user(role)).get(self.url).status_code, 200, role)

    def test_missing_decree_is_404(self):
        Municipality.objects.filter(pk=self.town.pk).update(governor_decree='')
        self.assertEqual(client_for(make_user('admin')).get(self.url).status_code, 404)


class SinglePageForm(TestCase):
    def test_one_page_with_a_single_submit_button(self):
        cache.clear()
        html = self.client.get(reverse('main:register_municipality')).content.decode()
        self.assertIn('type="submit"', html)
        for gone in ('next-btn', 'prev-btn', 'step-indicator'):
            self.assertNotIn(gone, html)


class AjaxSubmit(TestCase):
    """The form posts with XHR (for the upload progress bar); success answers with the redirect target."""

    def setUp(self):
        cache.clear()
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        override = override_settings(PRIVATE_MEDIA_ROOT=root)
        override.enable()
        self.addCleanup(override.disable)
        self.p, self.c, self.d = place()

    def test_success_returns_json_redirect(self):
        response = self.client.post(reverse('main:register_municipality'),
                                    registration_data(self.p, self.c, self.d),
                                    headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'redirect': reverse('main:home')})
        self.assertEqual(Municipality.objects.count(), 1)

    def test_errors_still_render_the_form(self):
        response = self.client.post(reverse('main:register_municipality'), {},
                                    headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])

    def test_page_has_the_progress_bar(self):
        html = self.client.get(reverse('main:register_municipality')).content.decode()
        self.assertIn('role="progressbar"', html)
