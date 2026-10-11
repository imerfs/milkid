from django.test import TestCase

from main import geography
from main.models import CityVillage, County, District, Province, PropertyAdvertisement
from main.tests.helpers import make_municipality, make_user


def tree():
    p = Province.objects.create(name='خراسان جنوبی')
    c = County.objects.create(province=p, name='بیرجند')
    d = District.objects.create(county=c, name='مرکزی')
    v = CityVillage.objects.create(district=d, name='حاجی‌آباد', settlement_type='village')
    return p, c, d, v


class Resolve(TestCase):
    def test_full_chain_is_found_by_name_whatever_the_spelling(self):
        p, c, d, v = tree()
        found = geography.resolve('خراسان جنوبی', 'بیرجند', 'مرکزی', 'حاجی آباد')      # space instead of half-space
        self.assertEqual((found['province_fk'], found['county_fk'], found['district_fk'], found['city_village_fk']),
                         (p, c, d, v))

    def test_arabic_letters_match_persian_ones(self):
        p, *_ = tree()
        self.assertEqual(geography.resolve('خراسان جنوبي')['province_fk'], p)

    def test_unknown_village_still_resolves_the_levels_above_it(self):
        p, c, d, _ = tree()
        found = geography.resolve('خراسان جنوبی', 'بیرجند', 'مرکزی', 'روستای ناشناس')
        self.assertEqual((found['county_fk'], found['district_fk'], found['city_village_fk']), (c, d, None))

    def test_same_village_name_under_another_county_is_not_matched(self):
        tree()
        p2 = Province.objects.create(name='استان دیگر')
        c2 = County.objects.create(province=p2, name='شهرستان دیگر')
        d2 = District.objects.create(county=c2, name='مرکزی')
        other = CityVillage.objects.create(district=d2, name='حاجی‌آباد')
        found = geography.resolve('خراسان جنوبی', 'بیرجند', 'مرکزی', 'حاجی‌آباد')
        self.assertNotEqual(found['city_village_fk'], other)

    def test_district_may_be_missing_and_the_settlement_is_found_through_the_county(self):
        _, c, _, v = tree()
        found = geography.resolve('خراسان جنوبی', 'بیرجند', '', 'حاجی‌آباد')
        self.assertEqual((found['county_fk'], found['city_village_fk']), (c, v))

    def test_empty_or_unknown_input_resolves_to_nothing(self):
        tree()
        self.assertEqual(set(geography.resolve().values()), {None})
        self.assertEqual(set(geography.resolve('جایی که نیست').values()), {None})


class SaveKeepsLinksInSync(TestCase):
    def test_profile_links_follow_the_text_it_is_saved_with(self):
        p, c, d, v = tree()
        profile = make_user('citizen').profile
        profile.province, profile.county, profile.district, profile.city_village = (
            'خراسان جنوبی', 'بیرجند', 'مرکزی', 'حاجی‌آباد')
        profile.save()
        profile.refresh_from_db()
        self.assertEqual((profile.province_fk, profile.county_fk, profile.district_fk, profile.city_village_fk),
                         (p, c, d, v))

    def test_links_are_cleared_when_the_text_is_cleared(self):
        tree()
        profile = make_user('citizen').profile
        profile.province, profile.county = 'خراسان جنوبی', 'بیرجند'
        profile.save()
        profile.province = profile.county = ''
        profile.save()
        profile.refresh_from_db()
        self.assertIsNone(profile.province_fk)
        self.assertIsNone(profile.county_fk)

    def test_partial_saves_that_do_not_touch_geography_leave_links_alone(self):
        p, *_ = tree()
        profile = make_user('citizen').profile
        profile.province = 'خراسان جنوبی'
        profile.save()
        profile.father_name = 'نام پدر'
        profile.save(update_fields=['father_name'])
        profile.refresh_from_db()
        self.assertEqual(profile.province_fk, p)

    def test_a_partial_save_of_the_text_also_saves_the_links(self):
        p, *_ = tree()
        profile = make_user('citizen').profile
        profile.province = 'خراسان جنوبی'
        profile.save(update_fields=['province'])
        profile.refresh_from_db()
        self.assertEqual(profile.province_fk, p)

    def test_municipality_and_advertisement_get_links_too(self):
        p, c, d, v = tree()
        town = make_municipality(make_user('dehyari'), village='حاجی‌آباد')        # province/county 'خراسان جنوبی'/'بیرجند'
        town.district = 'مرکزی'
        town.save()
        town.refresh_from_db()
        self.assertEqual((town.province_fk, town.county_fk, town.district_fk, town.city_village_fk), (p, c, d, v))
        self.assertTrue(hasattr(PropertyAdvertisement, 'city_village_fk'))


class Backfill(TestCase):
    def test_rows_written_without_save_get_their_links_from_the_migration_helper(self):
        p, c, d, v = tree()
        profile = make_user('citizen').profile
        type(profile).objects.filter(pk=profile.pk).update(
            province='خراسان جنوبی', county='بیرجند', district='مرکزی', city_village='حاجی‌آباد')   # bypasses save()
        from django.apps import apps
        geography.backfill(apps)
        profile.refresh_from_db()
        self.assertEqual((profile.province_fk, profile.city_village_fk), (p, v))


class GeoCheckReportsUnlinkedRows(TestCase):
    def test_a_profile_whose_province_matches_nothing_is_reported(self):
        from main.management.commands.geo_check import collect
        profile = make_user('citizen').profile
        type(profile).objects.filter(pk=profile.pk).update(province='استانی که وجود ندارد')
        _, soft, _ = collect()
        self.assertTrue(any('UserProfile rows name a province that matches no geography row' in line for line in soft))
