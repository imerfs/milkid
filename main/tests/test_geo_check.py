from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from main.management.commands.geo_check import collect, norm
from main.models import CityVillage, County, District, Province


class GeoCheck(TestCase):
    def build(self):
        province = Province.objects.create(name='استان آزمون')
        county = County.objects.create(province=province, name='شهرستان')
        district = District.objects.create(county=county, name='بخش')
        return province, county, district

    def test_spelling_variants_ignore_half_space_and_arabic_letters(self):
        self.assertEqual(norm('حاجی‌آباد'), norm('حاجی آباد'))
        self.assertEqual(norm('كرمان'), norm('کرمان'))

    def test_reports_two_spellings_in_one_district_and_missing_villages(self):
        _, _, district = self.build()
        CityVillage.objects.create(district=district, name='امیر آباد', settlement_type='village')
        CityVillage.objects.create(district=district, name='امیرآباد', settlement_type='village')
        hard, soft, _ = collect()
        self.assertTrue(any('settlements spelled two ways' in line for line in soft))
        self.assertTrue(any('provinces' in line for line in hard))     # 1 province, not 31

    def test_flags_a_county_without_districts_as_a_hard_problem(self):
        province, _, _ = self.build()
        County.objects.create(province=province, name='خالی')
        hard, _, _ = collect()
        self.assertIn('counties without districts: 1', hard)

    def test_command_runs_and_fails_on_hard_problems(self):
        self.build()
        with self.assertRaises(SystemExit):
            call_command('geo_check', stdout=StringIO())
