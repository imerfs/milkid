from django.core.management import call_command
from django.test import TestCase

from main.management.commands.geo_check import collect
from main.management.commands.geo_dedupe import plan
from main.models import CityVillage, County, Province


class GeographyFixture(TestCase):
    """`manage.py loaddata geography` is how a fresh server gets provinces, counties, districts and settlements."""

    @classmethod
    def setUpTestData(cls):
        call_command('loaddata', 'geography', verbosity=0)

    def test_loads_all_31_provinces_with_counties(self):
        self.assertEqual(Province.objects.count(), 31)
        self.assertEqual(County.objects.filter(province__name='تهران').exists(), True)

    def test_passes_the_hard_checks_and_has_no_double_spellings(self):
        hard, _, _ = collect()
        self.assertEqual(hard, [])
        self.assertEqual(plan(), [])

    def test_reference_data_carries_no_municipality_links(self):
        self.assertFalse(CityVillage.objects.exclude(municipality=None).exists())
        self.assertFalse(CityVillage.objects.filter(has_municipality=True).exists())
