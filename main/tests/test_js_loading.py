import re

from django.test import TestCase
from django.urls import reverse


class ScriptLoading(TestCase):
    def page(self):
        html = self.client.get(reverse('main:about')).content.decode()
        return re.sub(r'<!--.*?-->', '', html, flags=re.S)  # ignore commented-out scripts

    def test_local_scripts_never_block_parsing(self):
        for tag in re.findall(r'<script\b[^>]*\bsrc="[^"]*/static/js/[^"]*"[^>]*>', self.page()):
            if 'theme-init.js' in tag:  # must run early to avoid a theme flash
                continue
            self.assertIn('defer', tag, tag)

    def test_optional_enhancements_load_after_first_paint(self):
        page = self.page()
        for name in ('voice-ui', 'onboarding', 'keyboard-shortcuts'):
            self.assertNotRegex(page, r'<script[^>]+src="[^"]*%s\.js"' % name)
            self.assertIn(f'js/{name}.js', page)  # still referenced, by the idle loader

    def test_text_responses_are_gzipped(self):
        r = self.client.get(reverse('main:about'), HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(r.get('Content-Encoding'), 'gzip')


class TailwindIsPrebuilt(TestCase):
    """The Tailwind Play CDN (a ~300 KB runtime compiler) was replaced by a prebuilt stylesheet."""

    def test_no_template_loads_the_tailwind_cdn_or_runtime_config(self):
        from pathlib import Path
        offenders = [p.name for p in Path('main/templates').rglob('*.html')
                     if 'cdn.tailwindcss.com' in p.read_text(encoding='utf-8')
                     or 'tailwind.config' in p.read_text(encoding='utf-8')]
        self.assertEqual(offenders, [])

    def test_built_stylesheet_covers_the_classes_the_pages_rely_on(self):
        from django.contrib.staticfiles import finders
        path = finders.find('css/tailwind.css')
        self.assertTrue(path)
        css = open(path, encoding='utf-8').read()
        self.assertLess(len(css), 150_000)
        for selector in ('.bg-primary-600', '.animate-fade-in', '.md\:w-1\/2', '.dark\:hover\:bg-gray-700', '.font-vazir'):
            self.assertIn(selector, css)

    def test_standalone_pages_link_the_built_stylesheet_last(self):
        page = self.client.get(reverse('main:home')).content.decode()
        self.assertIn('css/tailwind.css', page)
        self.assertLess(page.index('css/melkid-design.css'), page.index('css/tailwind.css'))


class NoFullPageLoader(TestCase):
    def test_navigation_does_not_show_a_blocking_page_loader(self):
        from pathlib import Path
        js = Path('static/js/modern-interactions.js').read_text(encoding='utf-8')
        self.assertNotIn('page-loader', js)
        self.assertNotIn('showPageLoading', js)
