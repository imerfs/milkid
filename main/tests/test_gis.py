# pylint: disable=import-error  # shapely is optional (scripts/gis/requirements.txt); the tests using it skip without it
"""Village web-GIS: who may open Dastgerd's map, what the archive accepts, and that a reload keeps the archives."""
import json
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import TestCase
from django.urls import reverse

from main import geography, models as all_models
from main.gis import loader
from main.models import (CityVillage, County, District, MapParcel, ParcelArchive, ParcelFeePayment, Province,
                         VillageMap)
from main.tests.helpers import client_for, make_user

try:
    import shapely  # noqa: F401  pylint: disable=unused-import
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False

SLUG = 'dastgerd'
LOCAL = dict(province='خراسان جنوبی', county='بیرجند', city_village='دستگرد')   # a profile of the village's staff


def post_json(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


class MapIsLoaded(TestCase):
    def test_migration_loaded_dastgerd(self):
        village = VillageMap.objects.get(slug=SLUG)
        self.assertEqual(village.county_name, 'بیرجند')
        self.assertGreater(village.parcels.count(), 3000)
        self.assertGreater(village.blocks.count(), 250)
        self.assertTrue(village.parcels.filter(kind='estimated').exists())
        self.assertTrue(village.parcels.exclude(renewal_code='').exists())

    def test_every_plot_is_a_polygon_near_the_village(self):
        village = VillageMap.objects.get(slug=SLUG)
        for parcel in village.parcels.all()[:300]:
            lng, lat = parcel.geometry['coordinates'][0][0]
            self.assertTrue(59.2 < lng < 59.4 and 32.85 < lat < 32.97, (parcel.pk, lng, lat))


class MapAccess(TestCase):
    def urls(self, parcel):
        return {
            'page': reverse('main:gis_map', args=[SLUG]),
            'data': reverse('main:gis_data', args=[SLUG]),
            'detail': reverse('main:gis_parcel', args=[SLUG, parcel.pk]),
        }

    def setUp(self):
        self.parcel = MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='').first()

    def test_anonymous_is_sent_to_login_or_refused(self):
        urls = self.urls(self.parcel)
        self.assertEqual(client_for().get(urls['page']).status_code, 302)
        self.assertEqual(client_for().get(urls['data']).status_code, 401)
        self.assertEqual(client_for().get(urls['detail']).status_code, 401)
        self.assertEqual(post_json(client_for(), reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk]), {}).status_code, 401)

    def test_other_roles_are_refused_even_in_the_village(self):
        urls = self.urls(self.parcel)
        for role in ('citizen', 'owner', 'dehyari', 'inspector', 'accountant', 'council'):
            client = client_for(make_user(role, **LOCAL))
            with self.subTest(role=role):
                self.assertEqual(client.get(urls['page']).status_code, 302)
                self.assertEqual(client.get(urls['data']).status_code, 403)
                self.assertEqual(client.get(urls['detail']).status_code, 403)
                self.assertEqual(post_json(client, reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk]),
                                           {'owner_name': 'x'}).status_code, 403)
        self.assertFalse(ParcelArchive.objects.exists())

    def test_engineer_of_another_village_is_refused(self):
        urls = self.urls(self.parcel)
        for extra in (dict(province='خراسان جنوبی', county='بیرجند', city_village='ولدآباد'),
                      dict(province='یزد', county='یزد', city_village='دستگرد')):          # same name, other county
            with self.subTest(extra=extra):
                client = client_for(make_user('engineer', **extra))
                self.assertEqual(client.get(urls['data']).status_code, 403)
                self.assertEqual(client.get(urls['page']).status_code, 302)

    def test_engineer_without_a_village_is_refused(self):
        self.assertEqual(client_for(make_user('engineer')).get(self.urls(self.parcel)['data']).status_code, 403)

    def test_engineer_of_dastgerd_reaches_everything(self):
        client = client_for(make_user('engineer', **LOCAL))
        urls = self.urls(self.parcel)
        self.assertEqual(client.get(urls['page']).status_code, 200)
        data = client.get(urls['data'])
        self.assertEqual(data.status_code, 200)
        kinds = {f['properties']['t'] for f in data.json()['features']}
        self.assertEqual(kinds, {'b', 'p'})
        self.assertEqual(client.get(urls['detail']).json()['parcel']['code'], self.parcel.renewal_code)

    def test_engineer_linked_through_the_divisions_table_is_matched_by_link(self):
        province = Province.objects.create(name='خراسان جنوبی')
        county = County.objects.create(name='بیرجند', province=province)
        district = District.objects.create(name='مرکزی', county=county)
        village = CityVillage.objects.create(name='دستگرد', district=district, settlement_type='village')
        VillageMap.objects.filter(slug=SLUG).update(city_village=village)
        urls = self.urls(self.parcel)
        linked = make_user('engineer', city_village_fk=village, city_village='نام دیگر', county='جای دیگر')
        self.assertEqual(client_for(linked).get(urls['data']).status_code, 200)
        other = CityVillage.objects.create(name='دستگرد', district=District.objects.create(name='دیگر', county=county),
                                           settlement_type='village')
        stranger = make_user('engineer', city_village_fk=other, **LOCAL)      # same name, other village row
        self.assertEqual(client_for(stranger).get(urls['data']).status_code, 403)

    def test_admin_may_open_the_map(self):
        self.assertEqual(client_for(make_user('admin')).get(self.urls(self.parcel)['data']).status_code, 200)

    def test_map_data_is_never_cached(self):
        client = client_for(make_user('engineer', **LOCAL))
        self.assertIn('no-store', client.get(self.urls(self.parcel)['data'])['Cache-Control'])

    def test_expert_dashboard_links_to_the_map_only_for_its_village(self):
        link = reverse('main:gis_map', args=[SLUG])
        mine = client_for(make_user('engineer', **LOCAL)).get(reverse('main:dehyari_expert_dashboard'))
        self.assertContains(mine, link)
        other = client_for(make_user('engineer', province='خراسان جنوبی', county='بیرجند', city_village='ولدآباد'))
        self.assertNotContains(other.get(reverse('main:dehyari_expert_dashboard')), link)


class ArchiveAndPayments(TestCase):
    def setUp(self):
        self.parcel = MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='').first()
        self.user = make_user('engineer', **LOCAL)
        self.client = client_for(self.user)
        self.save_url = reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk])
        self.pay_url = reverse('main:gis_payment_add', args=[SLUG, self.parcel.pk])

    def test_a_plot_starts_with_an_empty_archive(self):
        parcel = self.client.get(reverse('main:gis_parcel', args=[SLUG, self.parcel.pk])).json()['parcel']
        self.assertEqual(parcel['archive']['owner_name'], '')
        self.assertEqual(parcel['payments'], [])

    def test_saving_the_archive(self):
        response = post_json(self.client, self.save_url, {
            'permit_number': 'P-12', 'permit_date': '۱۴۰۴/۰۲/۱۱', 'permit_type': 'مسکونی',
            'owner_name': 'علی دستگردی', 'owner_national_id': '۰۱۲۳۴۵۶۷۸۹', 'owner_phone': '09151234567'})
        self.assertEqual(response.status_code, 200, response.content)
        archive = ParcelArchive.objects.get(parcel=self.parcel)
        self.assertEqual((archive.permit_number, archive.owner_national_id), ('P-12', '0123456789'))
        self.assertEqual(archive.permit_date.isoformat(), '2025-05-01')
        self.assertEqual(archive.updated_by, self.user)
        self.assertEqual(response.json()['parcel']['archive']['permit_date'], '1404/02/11')

    def test_saving_again_updates_the_same_archive(self):
        post_json(self.client, self.save_url, {'owner_name': 'الف'})
        post_json(self.client, self.save_url, {'owner_name': 'ب'})
        self.assertEqual(ParcelArchive.objects.filter(parcel=self.parcel).count(), 1)
        self.assertEqual(ParcelArchive.objects.get(parcel=self.parcel).owner_name, 'ب')

    def test_bad_values_are_refused_and_nothing_is_saved(self):
        for body in ({'owner_national_id': '123'}, {'owner_national_id': 'abcdefghij'}, {'permit_date': '1404-13-45'},
                     {'permit_date': 'امروز'}, {'owner_phone': '09x'}, {'owner_name': 'x' * 200}):
            with self.subTest(body=body):
                self.assertEqual(post_json(self.client, self.save_url, body).status_code, 400)
        self.assertFalse(ParcelArchive.objects.exists())

    def test_archive_text_is_returned_as_data_not_html(self):
        post_json(self.client, self.save_url, {'owner_name': '<script>alert(1)</script>'})
        response = self.client.get(reverse('main:gis_parcel', args=[SLUG, self.parcel.pk]))
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['parcel']['archive']['owner_name'], '<script>alert(1)</script>')

    def test_adding_and_removing_a_payment(self):
        response = post_json(self.client, self.pay_url, {
            'fee_type': 'عوارض نوسازی', 'amount': '۱٬۲۵۰٬۰۰۰', 'fiscal_year': '۱۴۰۴', 'paid_on': '1404/03/01',
            'receipt_no': 'R-77'})
        self.assertEqual(response.status_code, 200, response.content)
        payment = ParcelFeePayment.objects.get(parcel=self.parcel)
        self.assertEqual((int(payment.amount), payment.fiscal_year, payment.created_by), (1250000, 1404, self.user))
        self.assertEqual(response.json()['parcel']['payments_total'], 1250000)
        delete = reverse('main:gis_payment_delete', args=[SLUG, self.parcel.pk, payment.pk])
        self.assertEqual(post_json(self.client, delete, {}).status_code, 200)
        self.assertFalse(ParcelFeePayment.objects.exists())

    def test_bad_payments_are_refused(self):
        for body in ({'fee_type': '', 'amount': '100'}, {'fee_type': 'x', 'amount': '0'}, {'fee_type': 'x', 'amount': '-5'},
                     {'fee_type': 'x', 'amount': '12.5'}, {'fee_type': 'x', 'amount': '5', 'fiscal_year': '99'},
                     {'fee_type': 'x', 'amount': '5', 'paid_on': 'دیروز'}):
            with self.subTest(body=body):
                self.assertEqual(post_json(self.client, self.pay_url, body).status_code, 400)
        self.assertFalse(ParcelFeePayment.objects.exists())

    def test_a_plot_of_another_village_is_not_reachable_through_this_one(self):
        other = VillageMap.objects.create(slug='other', name='جای دیگر')
        foreign = MapParcel.objects.create(village_map=other, uid='1-1', geometry={'type': 'Polygon', 'coordinates': []})
        response = self.client.get(reverse('main:gis_parcel', args=[SLUG, foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(post_json(self.client, reverse('main:gis_archive_save', args=[SLUG, foreign.pk]),
                                   {'owner_name': 'x'}).status_code, 404)
        self.assertFalse(ParcelArchive.objects.exists())

    def test_get_is_not_allowed_on_write_endpoints(self):
        self.assertEqual(self.client.get(self.save_url).status_code, 405)
        self.assertEqual(self.client.get(self.pay_url).status_code, 405)


class ReloadKeepsArchives(TestCase):
    def test_reloading_the_same_drawing_changes_nothing_and_keeps_the_archive(self):
        parcel = MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='').first()
        ParcelArchive.objects.create(parcel=parcel, owner_name='مالک')
        ParcelFeePayment.objects.create(parcel=parcel, fee_type='x', amount=10)
        before = MapParcel.objects.filter(village_map__slug=SLUG).count()
        result = loader.load_village_map(SLUG, all_models, geography=geography)
        self.assertEqual(result['parcels_created'], 0)
        self.assertEqual(result['parcels_removed'], 0)
        self.assertEqual(MapParcel.objects.filter(village_map__slug=SLUG).count(), before)
        self.assertEqual(ParcelArchive.objects.get(parcel__pk=parcel.pk).owner_name, 'مالک')
        self.assertEqual(ParcelFeePayment.objects.filter(parcel_id=parcel.pk).count(), 1)

    def test_a_plot_with_an_archive_survives_a_drawing_that_no_longer_has_it(self):
        keep, drop = list(MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='')[:2])
        ParcelArchive.objects.create(parcel=keep, owner_name='مالک')
        collection = json.loads(loader.VILLAGES[SLUG]['file'].read_text(encoding='utf-8'))
        collection['features'] = [f for f in collection['features'] if f['properties'].get('code') not in
                                  (keep.renewal_code, drop.renewal_code) or f['properties']['type'] == 'block']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'smaller.geojson'
            path.write_text(json.dumps(collection, ensure_ascii=False), encoding='utf-8')
            loader.load_village_map(SLUG, all_models, geography=geography, geojson_path=path)
        self.assertTrue(MapParcel.objects.filter(pk=keep.pk).exists())
        self.assertFalse(MapParcel.objects.filter(pk=drop.pk).exists())

    def test_uids_are_unique_and_stable(self):
        features = [f for f in json.loads(loader.VILLAGES[SLUG]['file'].read_text(encoding='utf-8'))['features']
                    if f['properties']['type'] == 'parcel']
        first, second = loader.parcel_uids(features), loader.parcel_uids(features)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), len(features))


@skipUnless(HAVE_SHAPELY, 'shapely is only needed to rebuild the map from a drawing (scripts/gis/requirements.txt)')
class BuildFromDrawing(TestCase):
    def test_renewal_code_is_block_dash_plot(self):
        from scripts.gis.build_village_map import renewal_code
        self.assertEqual(renewal_code('69', '12'), '69-12')
        self.assertEqual(renewal_code('', '12'), '')
        self.assertEqual(renewal_code('69', ''), '')

    def test_numbers_without_an_outline_split_the_free_block_area(self):
        from shapely.geometry import Point, box
        from scripts.gis.build_village_map import estimate_missing_plots
        block = box(0, 0, 40, 10)
        drawn = [box(0, 0, 10, 10)]
        points = [(Point(15, 5), '2'), (Point(25, 5), '3'), (Point(35, 5), '4')]
        result = dict(estimate_missing_plots(block, drawn, points))
        self.assertEqual(sorted(result), ['2', '3', '4'])
        self.assertAlmostEqual(sum(p.area for p in result.values()), 300, delta=0.01)   # the whole free area
        for number, point in ((n, p) for p, n in points):
            self.assertTrue(result[number].contains(point))
        self.assertFalse(any(p.intersects(drawn[0].buffer(-0.01)) for p in result.values()))

    def test_a_single_number_gets_the_whole_free_area(self):
        from shapely.geometry import Point, box
        from scripts.gis.build_village_map import estimate_missing_plots
        result = estimate_missing_plots(box(0, 0, 10, 10), [], [(Point(5, 5), '7')])
        self.assertEqual([n for n, _ in result], ['7'])
        self.assertAlmostEqual(result[0][1].area, 100)
