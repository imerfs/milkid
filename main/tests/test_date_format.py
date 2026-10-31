"""One date format on the whole site: Jalali YYYY/MM/DD with Persian digits, shown by the jalali filters (never Gregorian |date:), and one date field component
on every page that has a date input."""
import re
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_user

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'


def render(text, **ctx):
    return Template('{% load jalali_tags %}' + text).render(Context(ctx))


class Filters(SimpleTestCase):
    def test_a_date_is_jalali_with_persian_digits(self):
        self.assertEqual(render('{{ d|jalali_date }}', d=date(2026, 10, 31)), '۱۴۰۵/۰۸/۰۹')
        self.assertEqual(render('{{ d|jalali_date }}', d='2026-10-31'), '۱۴۰۵/۰۸/۰۹')

    def test_an_aware_datetime_is_shown_in_tehran_time(self):
        moment = datetime(2026, 10, 30, 21, 0, tzinfo=dt_timezone.utc)          # 00:30 on the 31st in Tehran
        self.assertEqual(render('{{ d|jalali_datetime }}', d=moment), '۱۴۰۵/۰۸/۰۹ ۰۰:۳۰')

    def test_empty_stays_empty(self):
        self.assertEqual(render('{{ d|jalali_date }}', d=None), '')


class NoGregorianDatesAreShown(SimpleTestCase):
    def test_no_template_prints_a_gregorian_date(self):
        bad = re.compile(r'\|date:["\'](Y/m/d|Y/m/d H:i|Y-m-d H:i|j F Y)["\']')
        found = [str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob('*.html') if bad.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(found, [])

    def test_every_date_filter_is_loaded_where_used(self):
        missing = []
        for p in TEMPLATES.rglob('*.html'):
            text = p.read_text(encoding='utf-8')
            if re.search(r'\|jalali_(date|datetime|short)', text) and not re.search(r'\{%\s*load[^%]*jalali_tags', text) and '{% extends' not in text[:0]:
                # a partial may rely on its parent's load only if it is an include; the filter would then fail at render time
                missing.append(str(p.relative_to(TEMPLATES)))
        self.assertEqual(missing, [])


class OneComponent(TestCase):
    def test_pages_with_date_fields_load_the_date_component(self):
        for name, who in (('main:register_citizen', None), ('main:dehyari_expert_dashboard', make_user('engineer')), ('main:clerk_dashboard', make_user('clerk'))):
            page = (client_for(who) if who else self.client).get(reverse(name))
            self.assertContains(page, 'jalali-datepicker.js', msg_prefix=name)

    def test_the_component_script_exists_and_knows_the_site_format(self):
        script = (TEMPLATES.parents[1] / 'static' / 'js' / 'jalali-datepicker.js').read_text(encoding='utf-8')
        for needle in ('type="date"', 'datetime-local', 'Keyline', 'YYYY/MM/DD'):
            self.assertIn(needle.replace('"', '') if needle.startswith('type') else needle, script.replace('"', '') if needle.startswith('type') else script)
