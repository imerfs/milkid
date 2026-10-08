import re
from pathlib import Path

from django.test import SimpleTestCase


class ViewImports(SimpleTestCase):
    def test_views_package_has_no_broken_relative_imports(self):
        """`from .models import X` inside main/views/ points at main.views.models, which does not exist."""
        pattern = re.compile(r'^\s*from \.(models|forms|services|search|validators|reports|messaging_views|api_views)\b', re.M)
        bad = [p.name for p in Path(__file__).resolve().parents[1].joinpath('views').glob('*.py')
               if pattern.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(bad, [])
