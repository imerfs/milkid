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
        for rule in ('.theme-toggle', '.gesture-enabled::after', '.voice-button', '.tutorial-trigger', '.mk-drawer-open'):
            self.assertIn(rule, phone)

    def test_tailwind_pages_have_no_default_body_margin(self):
        self.assertIn('body.mk-tw { margin: 0; }', self.css)
