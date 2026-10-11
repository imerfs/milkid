"""Phone layout guards. Layout itself is checked in a browser at 375px; these keep the known regressions out."""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_user


class PanelMenusOnPhones(TestCase):
    def html(self, role, url_name):
        return client_for(make_user(role)).get(reverse(url_name)).content.decode()

    def test_accountant_menu_starts_closed_and_opens_from_the_button(self):
        html = self.html('accountant', 'main:accountant_dashboard')
        self.assertIn('translate-x-full md:translate-x-0', html)      # closed on phones, always open on desktop
        self.assertNotIn('translate-x-0 md:translate-x-0', html)      # the old always-open state
        self.assertIn('id="sidebar-toggle"', html)

    def test_expert_panel_has_a_real_phone_menu(self):
        html = self.html('engineer', 'main:dehyari_expert_dashboard')
        self.assertIn('id="expert-sidebar"', html)
        self.assertIn('toggleExpertMenu()', html)
        self.assertNotIn("alert('منو", html)                          # the button used to only show an alert


class PhoneStylesheet(TestCase):
    css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'melkid-design.css').read_text(encoding='utf-8')

    def test_legacy_floating_widgets_are_calmed_on_phones(self):
        phone = self.css.split('max-width: 767.98px', 1)[1]
        for rule in ('.theme-toggle', '.voice-button', '.tutorial-trigger', '.mk-drawer-open'):
            self.assertIn(rule, phone)

    def test_tailwind_pages_have_no_default_body_margin(self):
        self.assertIn('body.mk-tw { margin: 0; }', self.css)


class NoScrollHijacking(TestCase):
    """Fast flicks used to count as swipes that jumped to the top or bottom of the page or went back/forward."""

    def test_gesture_script_is_gone_and_no_scroll_snap_remains(self):
        root = Path(settings.BASE_DIR)
        self.assertFalse((root / 'static' / 'js' / 'gesture-navigation.js').exists())
        for css in (root / 'static' / 'css').glob('*.css'):
            if css.name == 'tailwind.css':
                continue            # only Tailwind's own reset variable, no snap behaviour
            self.assertNotIn('scroll-snap', css.read_text(encoding='utf-8'), css.name)
        html = (root / 'main' / 'templates' / 'base.html').read_text(encoding='utf-8')
        self.assertNotIn('gesture-navigation', html)


class AdminCharts(TestCase):
    def test_a_canvas_never_gets_a_second_chart_without_destroying_the_first(self):
        html = (Path(settings.BASE_DIR) / 'main' / 'templates' / 'main' / 'dashboards' / 'admin_dashboard.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('new Chart('), 1)                 # only inside freshChart()
        self.assertIn('Chart.getChart(canvas)', html)
