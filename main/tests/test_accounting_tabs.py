"""The tab registry is the one place a workspace tab is defined: menu, access levels and renderer must agree with it."""
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main.accounting import access_levels, tabs
from main.tests.helpers import client_for
from main.tests.test_accounting_ledger import LedgerBase
from main.views import accounting_panel

PANEL_TEMPLATES = Path(__file__).resolve().parent.parent / 'templates' / 'main' / 'accounting' / 'panel'


class RegistryTests(SimpleTestCase):
    def test_keys_are_unique_and_groups_exist(self):
        keys = [t.key for t in tabs.TAB_LIST]
        self.assertEqual(len(keys), len(set(keys)))
        groups = {g[0] for g in tabs.GROUPS}
        self.assertTrue(all(t.group in groups or not t.group for t in tabs.TAB_LIST))

    def test_every_tab_has_a_builder_and_a_template_or_the_register(self):
        builders = accounting_panel.all_builders()
        for tab in tabs.TAB_LIST:
            with self.subTest(tab=tab.key):
                self.assertIn(tab.key, builders)
                self.assertTrue(tab.register or (PANEL_TEMPLATES / f'_{tab.key}.html').exists(), 'no template for the tab')

    def test_every_builder_is_a_registered_tab(self):
        self.assertEqual(set(accounting_panel.all_builders()) - {t.key for t in tabs.TAB_LIST}, set())

    def test_access_areas_come_from_the_registry(self):
        self.assertEqual(set(access_levels.TAB_AREA), {t.key for t in tabs.TAB_LIST if t.area})
        self.assertTrue(all(t.area in access_levels.AREA_KEYS for t in tabs.TAB_LIST if t.area))
        self.assertEqual(set(access_levels.ALWAYS), {t.key for t in tabs.TAB_LIST if not t.area})

    def test_menu_has_every_tab_once_and_the_phone_menu_follows_the_flag(self):
        menu = tabs.menu()
        placed = [e['key'] for e in menu['top']] + [e['key'] for g in menu['groups'] for e in g['items'] if not e['query']]
        self.assertEqual(sorted(placed), sorted(t.key for t in tabs.TAB_LIST))
        self.assertEqual([e['key'] for e in menu['mobile']], [t.key for t in tabs.TAB_LIST if t.mobile is not None])
        drafts = [e for g in menu['groups'] for e in g['items'] if e['query']]
        self.assertEqual([(e['key'], e['query']) for e in drafts], [('vouchers', 'status=temporary')])

    def test_year_free_tabs_match_the_flag(self):
        self.assertEqual(set(accounting_panel.YEAR_TABS), {t.key for t in tabs.TAB_LIST if t.needs_year})


class MenuRenderTests(LedgerBase):
    def test_sidebar_and_phone_menu_render_from_the_registry(self):
        page = client_for(self.dehyar).get(reverse('main:accountant_dashboard'))
        for tab in tabs.TAB_LIST:
            self.assertContains(page, f'data-acc-tab="{tab.key}"')
        self.assertContains(page, 'name="ac-nav"')
        self.assertContains(page, 'data-acc-query="status=temporary"')
