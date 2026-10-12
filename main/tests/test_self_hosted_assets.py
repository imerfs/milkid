"""Pages must not depend on Google Fonts / jsDelivr / cdnjs: they are slow or blocked in Iran."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

EXTERNAL = re.compile(r'https?://(?:cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|fonts\.googleapis\.com|'
                      r'fonts\.gstatic\.com|unpkg\.com|code\.jquery\.com|cdn\.tailwindcss\.com)')
STATIC_REF = re.compile(r"{%\s*static\s+['\"]([^'\"]+)['\"]\s*%}")


class SelfHostedAssets(TestCase):
    templates = sorted((Path(settings.BASE_DIR) / 'main' / 'templates').rglob('*.html'))

    def test_no_template_loads_a_third_party_cdn(self):
        offenders = [p.name for p in self.templates if EXTERNAL.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(offenders, [])

    def test_no_stylesheet_or_script_of_ours_imports_from_a_cdn(self):
        static = Path(settings.BASE_DIR) / 'static'
        offenders = [str(p.relative_to(static)) for pattern in ('css/*.css', 'js/*.js')
                     for p in static.glob(pattern) if EXTERNAL.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(offenders, [])

    def test_every_vendored_file_a_template_points_at_exists(self):
        missing = set()
        for p in self.templates:
            for ref in STATIC_REF.findall(p.read_text(encoding='utf-8')):
                if ref.startswith(('vendor/', 'css/vazirmatn.css')) and not finders.find(ref):
                    missing.add(ref)
        self.assertEqual(sorted(missing), [])

    def test_font_awesome_font_files_are_all_present(self):
        css = Path(finders.find('vendor/fontawesome/css/all.min.css')).read_text(encoding='utf-8')
        for name in set(re.findall(r'\.\./webfonts/([\w.-]+)', css)):
            self.assertTrue(finders.find(f'vendor/fontawesome/webfonts/{name}'), name)

    def test_vazirmatn_stylesheet_points_at_the_local_font(self):
        css = Path(finders.find('css/vazirmatn.css')).read_text(encoding='utf-8')
        self.assertIn('../vendor/vazirmatn/Vazirmatn-variable.woff2', css)
        self.assertTrue(finders.find('vendor/vazirmatn/Vazirmatn-variable.woff2'))

    def test_public_pages_reference_the_local_copies(self):
        for name in ('home', 'about', 'login'):
            html = self.client.get(reverse(f'main:{name}')).content.decode()
            self.assertIn('/static/vendor/fontawesome/css/all.min.css', html, name)
            self.assertNotRegex(html, EXTERNAL, name)
