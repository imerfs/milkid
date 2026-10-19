"""Rial display and reading: the same table the browser script is tested against (static/js/tests/rial-cases.json)."""
import json
from pathlib import Path

from django.test import SimpleTestCase

from main.accounting.parse import parse_amount
from main.templatetags.accounting_tags import rial

CASES = json.loads((Path(__file__).resolve().parents[2] / 'static' / 'js' / 'tests' / 'rial-cases.json').read_text(encoding='utf-8'))


class RialCasesTests(SimpleTestCase):
    def test_amounts_are_shown_as_the_browser_shows_them(self):
        for case in CASES['show']:
            with self.subTest(amount=case['amount']):
                self.assertEqual(rial(case['amount']), case['shown'])

    def test_typed_amounts_are_read_as_the_browser_reads_them(self):
        for case in CASES['read']:
            with self.subTest(typed=case['typed']):
                self.assertEqual(parse_amount(case['typed']), case['amount'])
