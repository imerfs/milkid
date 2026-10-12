from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from main.models import CityVillage, County, District, Municipality, Province, ServiceRequest
from main.tests.helpers import make_request, make_user


def build():
    province = Province.objects.create(name='استان آزمون')
    county = County.objects.create(province=province, name='شهرستان')
    district = District.objects.create(county=county, name='بخش')
    return province, county, district


class GeoDedupe(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command('geo_dedupe', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        _, _, district = build()
        CityVillage.objects.create(district=district, name='امیر آباد', settlement_type='village')
        CityVillage.objects.create(district=district, name='امیر‌آباد', settlement_type='village')
        self.assertIn('Dry run', self.run_command())
        self.assertEqual(CityVillage.objects.count(), 2)

    def test_settlement_spellings_merge_and_everything_follows(self):
        province, county, district = build()
        plain = CityVillage.objects.create(district=district, name='حاجی آباد', settlement_type='village')
        half = CityVillage.objects.create(district=district, name='حاجی‌آباد', settlement_type='village')
        request = make_request()
        ServiceRequest.objects.filter(pk=request.pk).update(city_village=plain)         # real key pointing at the loser
        user = make_user('citizen')
        type(user.profile).objects.filter(pk=user.profile.pk).update(
            province=province.name, county=county.name, district=district.name, city_village=plain.name)
        other_place = make_user('citizen')                                              # same name elsewhere: untouched
        type(user.profile).objects.filter(pk=other_place.profile.pk).update(
            province='استان دیگر', county=county.name, district=district.name, city_village=plain.name)

        self.run_command('--apply')

        kept = CityVillage.objects.get(district=district)
        self.assertEqual(kept.pk, plain.pk)                                             # referenced row wins over the half-space one
        request.refresh_from_db()
        self.assertEqual(request.city_village_id, kept.pk)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.city_village, kept.name)
        other_place.profile.refresh_from_db()
        self.assertEqual(other_place.profile.city_village, 'حاجی آباد')
        self.assertFalse(CityVillage.objects.filter(pk=half.pk).exists())

    def test_without_references_the_half_space_spelling_is_kept(self):
        _, _, district = build()
        CityVillage.objects.create(district=district, name='شوکت آباد', settlement_type='village')
        half = CityVillage.objects.create(district=district, name='شوکت‌آباد', settlement_type='village')
        self.run_command('--apply')
        self.assertEqual(list(CityVillage.objects.values_list('pk', flat=True)), [half.pk])

    def test_duplicate_counties_merge_their_districts_and_settlements(self):
        province, county, district = build()
        twin = County.objects.create(province=province, name='شهر‌ستان')
        twin_district = District.objects.create(county=twin, name='بخش')
        CityVillage.objects.create(district=district, name='الف')
        CityVillage.objects.create(district=twin_district, name='الف')
        CityVillage.objects.create(district=twin_district, name='ب')
        user = make_user('citizen')
        type(user.profile).objects.filter(pk=user.profile.pk).update(
            province=province.name, county=twin.name, district='بخش', city_village='ب')

        self.run_command('--apply')

        self.assertEqual(County.objects.filter(province=province).count(), 1)
        self.assertEqual(District.objects.count(), 1)
        self.assertEqual(sorted(CityVillage.objects.values_list('name', flat=True)), ['الف', 'ب'])
        kept_county = County.objects.get(province=province)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.county, kept_county.name)

    def test_nothing_to_do_on_clean_data(self):
        build()
        self.assertIn('No duplicate spellings', self.run_command('--apply'))
