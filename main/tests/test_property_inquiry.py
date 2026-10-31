"""The citizen's property inquiry map: who may open it, what a plot card tells (and never tells), the search, the flags and the panel tab."""
import json
from unittest import mock, skipUnless

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from main.gis import inquiry, plan_flags
from main.models import MapParcel, ParcelArchive, ParcelLock, VillageMap
from main.tests.helpers import client_for, make_user

try:
    import shapely  # noqa: F401  pylint: disable=unused-import
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False

SLUG = 'dastgerd'
PRIVATE = ('owner', 'permit', 'lock', 'payment', 'archive', 'national', 'phone', 'debt')


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.map = VillageMap.objects.get(slug=SLUG)
        self.citizen = make_user('citizen')
        self.parcel = MapParcel.objects.filter(village_map=self.map).exclude(renewal_code='').first()

    def get(self, name, who=None, args=None, **query):
        return client_for(who or self.citizen).get(reverse(name, args=[SLUG] if args is None else args), query)


class Access(Base):
    def test_anonymous_is_sent_to_login_or_refused(self):
        self.assertEqual(client_for().get(reverse('main:property_inquiry')).status_code, 302)
        for name in ('inquiry_data', 'inquiry_search'):
            self.assertEqual(client_for().get(reverse(f'main:{name}', args=[SLUG])).status_code, 401, name)
        self.assertEqual(client_for().get(reverse('main:inquiry_parcel', args=[SLUG, self.parcel.pk])).status_code, 401)

    def test_citizens_and_every_kind_of_staff_may_open_it(self):
        for role in ('citizen', 'owner', 'resident', 'dehyari', 'engineer', 'clerk', 'inspector', 'accountant', 'council', 'admin'):
            who = make_user(role)
            self.assertEqual(client_for(who).get(reverse('main:property_inquiry')).status_code, 200, role)
            self.assertEqual(client_for(who).get(reverse('main:inquiry_data', args=[SLUG])).status_code, 200, role)

    def test_an_unknown_village_is_404_and_data_is_never_cached(self):
        self.assertEqual(client_for(self.citizen).get(reverse('main:inquiry_data', args=['nowhere'])).status_code, 404)
        self.assertIn('no-store', self.get('main:inquiry_data')['Cache-Control'])


class WhatIsShown(Base):
    def test_the_map_data_has_only_the_light_fields(self):
        data = self.get('main:inquiry_data').json()
        self.assertEqual(len(data['features']), self.map.parcels.count())
        self.assertEqual(set(data['features'][0]['properties']), {'n', 'b', 'c', 'z', 'a', 'u', 'p', 'x', 'e'})

    def test_the_card_never_carries_private_data(self):
        ParcelArchive.objects.create(parcel=self.parcel, owner_name='مالک خصوصی', permit_number='123')
        ParcelLock.objects.create(parcel=self.parcel, reason='debt', notes='بدهی ویژه', locked_by=make_user('dehyari'))
        body = json.dumps(self.get('main:inquiry_parcel', args=[SLUG, self.parcel.pk]).json(), ensure_ascii=False)
        self.assertNotIn('مالک خصوصی', body)
        self.assertNotIn('بدهی ویژه', body)
        for word in PRIVATE:
            self.assertNotIn('"' + word, body)

    def test_the_card_says_what_a_buyer_needs(self):
        MapParcel.objects.filter(pk=self.parcel.pk).update(in_plan=True, exempt=True)
        card = self.get('main:inquiry_parcel', args=[SLUG, self.parcel.pk]).json()['parcel']
        texts = ' '.join(s['text'] for s in card['status'])
        self.assertIn('داخل طرح', texts)
        self.assertIn('جزو مستثنیات', texts)
        self.assertEqual(card['code'], self.parcel.renewal_code)
        self.assertIn('استعلام رسمی', card['notice'])
        MapParcel.objects.filter(pk=self.parcel.pk).update(in_plan=False, exempt=False)
        texts = ' '.join(s['text'] for s in self.get('main:inquiry_parcel', args=[SLUG, self.parcel.pk]).json()['parcel']['status'])
        self.assertIn('خارج از طرح', texts)
        self.assertIn('جزو مستثنیات نیست', texts)

    def test_a_plot_asked_for_through_another_village_is_not_found(self):
        VillageMap.objects.create(slug='other', name='دیگر')
        self.assertEqual(self.get('main:inquiry_parcel', args=['other', self.parcel.pk]).status_code, 404)


class Search(Base):
    def results(self, q):
        return self.get('main:inquiry_search', q=q).json()['results']

    def test_by_renewal_code_persian_digits_too(self):
        code = self.parcel.renewal_code
        self.assertEqual([r['id'] for r in self.results(code)], [self.parcel.pk])
        persian = code.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
        self.assertEqual([r['id'] for r in self.results(persian)], [self.parcel.pk])

    def test_by_plot_and_block_in_either_order_and_by_number(self):
        ids = {r['id'] for r in self.results(f'{self.parcel.number}-{self.parcel.block_no}')}
        self.assertIn(self.parcel.pk, ids)
        ids = {r['id'] for r in self.results(f'{self.parcel.block_no}/{self.parcel.number}')}
        self.assertIn(self.parcel.pk, ids)
        self.assertTrue(self.results(self.parcel.number))

    def test_nonsense_and_empty_find_nothing_and_results_are_capped(self):
        for q in ('', 'abc', '1-2-3-4', "1' OR '1'='1", '١٢٣٤٥٦٧٨٩٠' * 3):
            self.assertEqual(self.results(q), [], q)
        self.assertLessEqual(len(self.results('1')), inquiry.MAX_RESULTS)


class Throttle(Base):
    def test_a_user_who_pulls_too_much_is_slowed_down(self):
        with mock.patch.dict('main.views.inquiry_views.LIMITS', {'search': (3, 3600)}):
            statuses = [self.get('main:inquiry_search', q='1').status_code for _ in range(5)]
        self.assertEqual(statuses, [200, 200, 200, 429, 429])


class Flags(Base):
    def test_the_flags_file_is_applied_to_the_plots(self):
        path = plan_flags.path_of(SLUG)
        self.assertTrue(path.exists())
        flags = json.loads(path.read_text(encoding='utf-8'))
        counts = plan_flags.apply(SLUG)
        self.assertEqual(counts, {'in_plan': len(flags['in_plan']), 'exempt': len(flags['exempt'])})
        self.assertGreater(counts['exempt'], 0)
        self.assertTrue(MapParcel.objects.get(village_map=self.map, uid=flags['exempt'][0]).exempt)

    def test_applying_twice_gives_the_same_result_and_a_missing_file_is_none(self):
        self.assertEqual(plan_flags.apply(SLUG), plan_flags.apply(SLUG))
        with mock.patch.object(plan_flags, 'path_of', return_value=plan_flags.path_of('absent')):
            self.assertIsNone(plan_flags.apply(SLUG))

    def test_the_map_is_recomputed_when_the_flags_change(self):
        plan_flags.apply(SLUG)
        before = sum(f['properties']['x'] for f in self.get('main:inquiry_data').json()['features'])
        MapParcel.objects.filter(village_map=self.map, exempt=True).update(exempt=False)
        after = sum(f['properties']['x'] for f in self.get('main:inquiry_data').json()['features'])
        self.assertGreater(before, after)
        self.assertEqual(after, 0)


@skipUnless(HAVE_SHAPELY, 'shapely is installed only where a map is rebuilt')
class FlagBuilder(TestCase):
    def test_a_plot_is_flagged_when_enough_of_it_lies_in_the_frame(self):
        from shapely.geometry import box
        from scripts.gis import build_plan_flags as build
        parcels = [('inside', box(0, 0, 1, 1)), ('half', box(2, 0, 3, 1)), ('out', box(5, 5, 6, 6))]
        frame = [box(-1, -1, 1.5, 2), box(2, -1, 2.6, 2)]
        self.assertEqual(sorted(build.flag(parcels, frame, 0.5)), ['half', 'inside'])
        self.assertEqual(sorted(build.flag(parcels, frame, 0.7)), ['inside'])


class Panel(Base):
    def test_the_citizen_panel_has_the_inquiry_tab(self):
        page = client_for(self.citizen).get(reverse('main:owner_dashboard'))
        self.assertContains(page, 'data-tab="inquiry"')
        self.assertContains(page, reverse('main:property_inquiry'))

    def test_the_page_renders_the_map_with_the_village_and_the_icons(self):
        page = self.get('main:property_inquiry', args=[])
        for needle in ('id="pi-map"', 'property-inquiry.js', 'روستای دستگرد', 'Keyline Icons', 'id="i-search"'):
            self.assertContains(page, needle)
        self.assertEqual(page.context['chosen'].slug, SLUG)

    def test_without_any_map_the_page_says_so(self):
        VillageMap.objects.all().delete()
        self.assertContains(self.get('main:property_inquiry', args=[]), 'هنوز نقشه‌ای')
