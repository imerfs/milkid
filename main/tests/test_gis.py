# pylint: disable=import-error  # shapely is optional (scripts/gis/requirements.txt); the tests using it skip without it
"""Village web-GIS: who may open Dastgerd's map, what the archive accepts, and that a reload keeps the archives."""
import json
import re
import tempfile
from pathlib import Path
from unittest import mock, skipUnless

from django.test import TestCase
from django.urls import reverse

from main import geography, models as all_models
from main.gis import data as gis_data, loader
from main.gis.uids import parcel_uids, renewal_code
from main.models import (CityVillage, County, District, LandUseClass, MapBuilding, MapEasement, MapParcel, MapZone,
                         ParcelArchive, ParcelFeePayment, ParcelLock, Province, VillageMap)
from main.tests.helpers import client_for, isolate_private_media, make_service, make_user

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
            'buildings': reverse('main:gis_buildings', args=[SLUG]),
            'easements': reverse('main:gis_easements', args=[SLUG]),
        }

    def setUp(self):
        self.parcel = MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='').first()

    def test_anonymous_is_sent_to_login_or_refused(self):
        urls = self.urls(self.parcel)
        self.assertEqual(client_for().get(urls['page']).status_code, 302)
        for name in ('data', 'detail', 'buildings', 'easements'):
            self.assertEqual(client_for().get(urls[name]).status_code, 401, name)
        self.assertEqual(post_json(client_for(), reverse('main:gis_lock', args=[SLUG, self.parcel.pk]), {}).status_code, 401)
        self.assertEqual(post_json(client_for(), reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk]), {}).status_code, 401)

    def test_other_roles_are_refused_even_in_the_village(self):
        urls = self.urls(self.parcel)
        for role in ('citizen', 'owner', 'inspector', 'accountant', 'council'):
            client = client_for(make_user(role, **LOCAL))
            with self.subTest(role=role):
                self.assertEqual(client.get(urls['page']).status_code, 302)
                for name in ('data', 'detail', 'buildings', 'easements'):
                    self.assertEqual(client.get(urls[name]).status_code, 403, name)
                self.assertEqual(post_json(client, reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk]),
                                           {'owner_name': 'x'}).status_code, 403)
                self.assertEqual(post_json(client, reverse('main:gis_lock', args=[SLUG, self.parcel.pk]),
                                           {'reason': 'debt'}).status_code, 403)
        self.assertFalse(ParcelArchive.objects.exists())
        self.assertFalse(ParcelLock.objects.exists())

    def test_the_dehyari_and_the_clerk_open_the_map_and_edit_plots_but_only_the_dehyari_locks(self):
        urls = self.urls(self.parcel)
        for role, may_lock in (('dehyari', True), ('clerk', False)):
            client = client_for(make_user(role, **LOCAL))
            with self.subTest(role=role):
                self.assertEqual(client.get(urls['page']).status_code, 200)
                for name in ('data', 'detail', 'buildings', 'easements'):
                    self.assertEqual(client.get(urls[name]).status_code, 200, name)
                saved = post_json(client, reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk]), {'owner_name': 'مالک آزمون'})
                self.assertEqual(saved.status_code, 200, saved.content[:200])
                locked = post_json(client, reverse('main:gis_lock', args=[SLUG, self.parcel.pk]), {'reason': 'debt'})
                self.assertEqual(locked.status_code == 200, may_lock, (role, locked.status_code))
                config = client.get(urls['page']).context['config']
                self.assertEqual((config['canEdit'], config['canLock']), (True, may_lock))
                ParcelLock.objects.all().delete()

    def test_the_dehyari_and_the_clerk_of_another_village_are_refused(self):
        urls = self.urls(self.parcel)
        for role in ('dehyari', 'clerk'):
            client = client_for(make_user(role, city_village='روستای دیگر', county='شهرستان دیگر'))
            self.assertEqual(client.get(urls['page']).status_code, 302, role)
            self.assertEqual(client.get(urls['data']).status_code, 403, role)

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
        body = data.json()
        self.assertEqual(set(body), {'parcels', 'blocks', 'zones', 'land_uses', 'centre'})
        self.assertGreater(len(body['parcels']['features']), 3000)
        self.assertEqual(len(body['zones']['features']), 6)
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
        first, second = parcel_uids(features), parcel_uids(features)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), len(features))


@skipUnless(HAVE_SHAPELY, 'shapely is only needed to rebuild the map from a drawing (scripts/gis/requirements.txt)')
class BuildFromDrawing(TestCase):
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


class RenewalCode(TestCase):
    def test_code_is_guild_apartment_plot_block_zone(self):
        self.assertEqual(renewal_code(0, 0, '12', '69', '3'), '0-0-12-69-3')
        self.assertEqual(renewal_code(5, 2, '7', '101', '4'), '5-2-7-101-4')

    def test_no_code_without_plot_block_or_zone(self):
        for args in ((0, 0, '', '69', '3'), (0, 0, '12', '', '3'), (0, 0, '12', '69', '')):
            self.assertEqual(renewal_code(*args), '')

    def test_every_stored_code_has_the_five_parts(self):
        pattern = re.compile(r'^\d+-\d+-\d+-\d+-[1-6]$')
        codes = list(MapParcel.objects.exclude(renewal_code='').values_list('renewal_code', flat=True))
        self.assertGreater(len(codes), 3000)
        self.assertEqual([c for c in codes if not pattern.match(c)][:5], [])

    def test_code_agrees_with_the_plots_own_fields(self):
        for parcel in MapParcel.objects.exclude(renewal_code='')[:400]:
            self.assertEqual(parcel.renewal_code, f'{parcel.guild_no}-{parcel.apartment_no}-{parcel.number}-{parcel.block_no}-{parcel.zone}')

    def test_most_plots_have_a_code_and_unnumbered_ones_do_not(self):
        total = MapParcel.objects.count()
        self.assertGreater(MapParcel.objects.exclude(renewal_code='').count(), 0.85 * total)
        self.assertFalse(MapParcel.objects.filter(number='').exclude(renewal_code='').exists())


class MapContents(TestCase):
    def setUp(self):
        self.village = VillageMap.objects.get(slug=SLUG)

    def test_six_neighbourhoods_each_with_a_polygon(self):
        zones = MapZone.objects.filter(village_map=self.village)
        self.assertEqual(sorted(z.number for z in zones), ['1', '2', '3', '4', '5', '6'])
        self.assertTrue(all(z.geometry['type'] in ('Polygon', 'MultiPolygon') and z.parcel_count > 100 for z in zones))

    def test_plots_belong_to_a_neighbourhood_and_a_block_has_one(self):
        self.assertLess(MapParcel.objects.filter(village_map=self.village, zone='').count(), 20)
        by_block = {}
        village = MapParcel.objects.exclude(zone='').exclude(zone='6').exclude(block_no='')   # block numbers of zone 6 restart at 1
        for block, zone in village.values_list('block_no', 'zone'):
            by_block.setdefault(block, []).append(zone)
        agree = sum(max(zs.count(z) for z in set(zs)) for zs in by_block.values())
        self.assertGreater(agree / sum(len(zs) for zs in by_block.values()), 0.98)

    def test_land_use_colours_come_from_the_drawing(self):
        classes = {c.key: c for c in LandUseClass.objects.filter(village_map=self.village)}
        self.assertGreater(len(classes), 10)
        self.assertEqual(classes['ffff00'].name, 'مسکونی')
        self.assertTrue(all(re.fullmatch(r'[0-9a-f]{6}', key) for key in classes))
        residential = MapParcel.objects.filter(land_use__key='ffff00').count()
        self.assertGreater(residential, 2000)

    def test_buildings_are_the_improvements_on_the_land(self):
        self.assertGreater(MapBuilding.objects.filter(village_map=self.village).count(), 3000)
        built = MapParcel.objects.filter(village_map=self.village, building_count__gt=0)
        self.assertGreater(built.count(), 2000)
        for parcel in built[:200]:
            self.assertGreater(parcel.building_area_m2, 0)
            self.assertLess(parcel.building_area_m2, parcel.area_m2 * 3 + 10)

    def test_easement_kinds_and_the_plots_that_break_them(self):
        kinds = set(MapEasement.objects.filter(village_map=self.village).values_list('kind', flat=True))
        self.assertTrue({'qanat', 'defense2', 'general'} <= kinds)
        hit = list(MapParcel.objects.exclude(easement_hits=[]))
        self.assertTrue(hit)
        for parcel in hit:
            self.assertTrue(all({'k', 'a'} <= set(h) for h in parcel.easement_hits))

    def test_timeline_marks_what_the_two_surveys_disagree_on(self):
        gone = MapParcel.objects.filter(last_year__isnull=False)
        self.assertTrue(gone.exists())
        self.assertEqual(set(gone.values_list('last_year', flat=True)), {1404})


class MapLayersEndpoints(TestCase):
    def setUp(self):
        self.client = client_for(make_user('engineer', **LOCAL))

    def test_buildings_and_easements_are_feature_collections(self):
        buildings = self.client.get(reverse('main:gis_buildings', args=[SLUG])).json()
        easements = self.client.get(reverse('main:gis_easements', args=[SLUG])).json()
        self.assertEqual(buildings['type'], 'FeatureCollection')
        self.assertGreater(len(buildings['features']), 3000)
        self.assertEqual({f['properties']['k'] for f in easements['features']} - {'general', 'quality', 'qanat', 'qanat_quality', 'defense1', 'defense2'}, set())

    def test_plots_carry_what_the_map_colours_by(self):
        features = self.client.get(reverse('main:gis_data', args=[SLUG])).json()['parcels']['features']
        props = features[0]['properties']
        for key in ('id', 'code', 'b', 'n', 'z', 'e', 'a', 'lu', 'ba', 'h', 'f', 'py', 'pay', 'lk', 'fy', 'ly'):
            self.assertIn(key, props)

    def test_the_page_hands_the_script_its_configuration(self):
        page = self.client.get(reverse('main:gis_map', args=[SLUG]))
        self.assertContains(page, 'id="vm-config"')
        self.assertContains(page, 'vm-timeline')
        self.assertContains(page, 'data-easement="qanat"')
        self.assertContains(page, 'name="colormode" value="use"')


class ParcelDetailShowsTheNewFacts(TestCase):
    def test_area_building_zone_land_use_and_violations(self):
        client = client_for(make_user('engineer', **LOCAL))
        violating = MapParcel.objects.exclude(easement_hits=[]).first()
        detail = client.get(reverse('main:gis_parcel', args=[SLUG, violating.pk])).json()['parcel']
        self.assertTrue(detail['easements'])
        self.assertTrue(all(e['label'] for e in detail['easements']))
        built = MapParcel.objects.filter(building_count__gt=0, land_use__key='ffff00').first()
        detail = client.get(reverse('main:gis_parcel', args=[SLUG, built.pk])).json()['parcel']
        self.assertEqual(detail['land_use']['name'], 'مسکونی')
        self.assertEqual(detail['land_use']['color'], '#ffff00')
        self.assertGreater(detail['building_area'], 0)
        self.assertEqual(detail['zone'], built.zone)
        self.assertEqual(detail['code'], built.renewal_code)


class LockingAParcel(TestCase):
    def setUp(self):
        self.parcel = MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='').first()
        self.user = make_user('engineer', **LOCAL)
        self.client = client_for(self.user)
        self.lock_url = reverse('main:gis_lock', args=[SLUG, self.parcel.pk])

    def test_locking_for_each_of_the_three_reasons(self):
        for reason in ('debt', 'neighbor_complaint', 'street_occupation'):
            response = post_json(self.client, self.lock_url, {'reason': reason, 'notes': 'یادداشت'})
            self.assertEqual(response.status_code, 200, response.content)
        parcel = response.json()['parcel']
        self.assertTrue(parcel['locked'])
        self.assertEqual({lock['reason'] for lock in parcel['locks']}, {'debt', 'neighbor_complaint', 'street_occupation'})
        self.assertEqual(ParcelLock.objects.filter(parcel=self.parcel, unlocked_at__isnull=True).count(), 3)
        self.assertTrue(all(lock.locked_by == self.user for lock in ParcelLock.objects.all()))

    def test_an_unknown_reason_or_a_repeat_is_refused(self):
        self.assertEqual(post_json(self.client, self.lock_url, {'reason': 'because'}).status_code, 400)
        self.assertEqual(post_json(self.client, self.lock_url, {}).status_code, 400)
        self.assertEqual(post_json(self.client, self.lock_url, {'reason': 'debt'}).status_code, 200)
        self.assertEqual(post_json(self.client, self.lock_url, {'reason': 'debt'}).status_code, 400)
        self.assertEqual(ParcelLock.objects.count(), 1)

    def test_releasing_needs_a_reason_and_keeps_the_history(self):
        post_json(self.client, self.lock_url, {'reason': 'debt'})
        lock = ParcelLock.objects.get()
        release = reverse('main:gis_unlock', args=[SLUG, self.parcel.pk, lock.pk])
        self.assertEqual(post_json(self.client, release, {'notes': ''}).status_code, 400)
        self.assertTrue(ParcelLock.objects.get().active)
        response = post_json(self.client, release, {'notes': 'بدهی پرداخت شد'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['parcel']['locked'])
        lock.refresh_from_db()
        self.assertEqual((lock.active, lock.unlocked_by, lock.unlock_notes), (False, self.user, 'بدهی پرداخت شد'))
        self.assertEqual(post_json(self.client, release, {'notes': 'دوباره'}).status_code, 404)    # already released
        self.assertEqual(post_json(self.client, self.lock_url, {'reason': 'debt'}).status_code, 200)  # can be locked again
        self.assertEqual(ParcelLock.objects.filter(parcel=self.parcel).count(), 2)

    def test_the_map_data_shows_who_is_locked_and_when(self):
        post_json(self.client, self.lock_url, {'reason': 'street_occupation'})
        features = self.client.get(reverse('main:gis_data', args=[SLUG])).json()['parcels']['features']
        props = next(f['properties'] for f in features if f['properties']['id'] == self.parcel.pk)
        start = gis_data.current_year()
        self.assertEqual(props['lk'], [[start, 0]])

    def test_a_plot_of_another_village_cannot_be_locked_through_this_one(self):
        other = VillageMap.objects.create(slug='other', name='جای دیگر')
        foreign = MapParcel.objects.create(village_map=other, uid='1-1', geometry={'type': 'Polygon', 'coordinates': []})
        response = post_json(self.client, reverse('main:gis_lock', args=[SLUG, foreign.pk]), {'reason': 'debt'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ParcelLock.objects.exists())

    def test_the_admin_may_lock_too(self):
        admin = client_for(make_user('admin'))
        self.assertEqual(post_json(admin, self.lock_url, {'reason': 'debt'}).status_code, 200)


class TimelineFlags(TestCase):
    def test_permit_payment_and_lock_years_reach_the_map(self):
        village = VillageMap.objects.get(slug=SLUG)
        parcel = MapParcel.objects.filter(village_map=village).exclude(renewal_code='').first()
        ParcelArchive.objects.create(parcel=parcel, owner_name='مالک', permit_date=__import__('datetime').date(2025, 5, 1))
        ParcelFeePayment.objects.create(parcel=parcel, fee_type='x', amount=5, paid_on=__import__('datetime').date(2024, 4, 1))
        flags = gis_data.live_flags(village)[parcel.pk]
        self.assertEqual((flags['f'], flags['py']), (1, 1404))        # 2025-05-01 is 1404/02/11
        self.assertEqual(flags['pay'], [1403])

    def test_an_archive_without_a_permit_date_has_no_permit_year(self):
        village = VillageMap.objects.get(slug=SLUG)
        parcel = MapParcel.objects.filter(village_map=village).first()
        ParcelArchive.objects.create(parcel=parcel, owner_name='مالک')
        flags = gis_data.live_flags(village)[parcel.pk]
        self.assertEqual((flags['f'], flags['py']), (1, None))


class LoaderKeepsWhatPeopleTyped(TestCase):
    def test_a_name_given_to_a_colour_and_a_zone_survives_a_reload(self):
        village = VillageMap.objects.get(slug=SLUG)
        LandUseClass.objects.filter(village_map=village).exclude(key='ffff00').update(name='نام تستی')
        MapZone.objects.filter(village_map=village, number='2').update(name='محله‌ی بالا')
        parcel = MapParcel.objects.filter(village_map=village).exclude(renewal_code='').first()
        ParcelLock.objects.create(parcel=parcel, reason='debt')
        loader.load_village_map(SLUG, all_models, geography=geography)
        self.assertTrue(LandUseClass.objects.filter(village_map=village, name='نام تستی').exists())
        self.assertEqual(MapZone.objects.get(village_map=village, number='2').name, 'محله‌ی بالا')
        self.assertTrue(ParcelLock.objects.filter(parcel=parcel, unlocked_at__isnull=True).exists())

    def test_a_plot_with_a_lock_survives_a_drawing_without_it(self):
        village = VillageMap.objects.get(slug=SLUG)
        keep = MapParcel.objects.filter(village_map=village).exclude(renewal_code='').first()
        ParcelLock.objects.create(parcel=keep, reason='debt')
        collection = json.loads(loader.VILLAGES[SLUG]['file'].read_text(encoding='utf-8'))
        collection['features'] = [f for f in collection['features'] if f['properties'].get('uid') != keep.uid]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'smaller.geojson'
            path.write_text(json.dumps(collection, ensure_ascii=False), encoding='utf-8')
            loader.load_village_map(SLUG, all_models, geography=geography, geojson_path=path)
        self.assertTrue(MapParcel.objects.filter(pk=keep.pk).exists())


@skipUnless(HAVE_SHAPELY, 'shapely is only needed to rebuild the map from a drawing (scripts/gis/requirements.txt)')
class BuildHelpers(TestCase):
    def test_two_parallel_lines_become_one_corridor_between_them(self):
        from shapely.geometry import LineString
        from scripts.gis.build_village_map import pair_corridors
        a = LineString([(0, 0), (100, 0)])
        b = LineString([(0, 15), (100, 15)])
        far = LineString([(0, 500), (100, 500)])
        corridors, rest = pair_corridors([a, b, far])
        self.assertEqual(len(corridors), 1)
        self.assertAlmostEqual(corridors[0].area, 1500, delta=1)
        self.assertEqual(len(rest), 1)                      # the lone line stays a line

    def test_a_short_stub_is_never_paired(self):
        from shapely.geometry import LineString
        from scripts.gis.build_village_map import pair_corridors
        corridors, rest = pair_corridors([LineString([(0, 0), (5, 0)]), LineString([(0, 2), (5, 2)])])
        self.assertEqual((corridors, len(rest)), ([], 2))

    def test_the_most_specific_solid_fill_decides_the_land_use(self):
        from shapely.geometry import Point, box
        from shapely.strtree import STRtree
        from scripts.gis.build_village_map import land_use_of
        fills = [(box(0, 0, 100, 100), 'big', 'ffff00', True), (box(40, 40, 60, 60), 'small', 'ff0000', True),
                 (box(0, 0, 100, 100), 'pattern', 'ffffff', False)]
        tree = STRtree([f[0] for f in fills])
        self.assertEqual(land_use_of(Point(50, 50), fills, tree), ('ff0000', 'small'))
        self.assertEqual(land_use_of(Point(10, 10), fills, tree), ('ffff00', 'big'))
        self.assertIsNone(land_use_of(Point(500, 500), fills, tree))

    def test_geometry_json_reprojects_every_shape(self):
        from shapely.geometry import LineString, MultiPolygon, box
        from scripts.gis.build_village_map import geometry_json
        shift = lambda x, y: (x + 1, y + 2)
        self.assertEqual(geometry_json(LineString([(0, 0), (1, 1)]), shift)['coordinates'], [[1, 2], [2, 3]])
        self.assertEqual(geometry_json(box(0, 0, 1, 1), shift)['type'], 'Polygon')
        self.assertEqual(geometry_json(MultiPolygon([box(0, 0, 1, 1), box(5, 5, 6, 6)]), shift)['type'], 'MultiPolygon')


class LockedPlotsGetNoServices(TestCase):
    """A locked plot is refused new requests, and requests naming it cannot be approved."""

    def setUp(self):
        self.parcel = MapParcel.objects.filter(village_map__slug=SLUG).exclude(renewal_code='').first()
        self.code = self.parcel.renewal_code
        self.citizen = make_user('citizen', **LOCAL)
        self.service = make_service()
    def lock(self, reason='debt'):
        return ParcelLock.objects.create(parcel=self.parcel, reason=reason)

    def submit(self, code):
        return client_for(self.citizen).post(reverse('main:dashboard_submit_request'), {
            'service': self.service.pk, 'title': 'درخواست', 'description': 'توضیح', 'parcel_number': code})

    def test_the_message_names_the_reason(self):
        from main.gis import locks
        self.assertEqual(locks.refusal(self.code), '')
        self.lock('debt')
        self.lock('street_occupation')
        message = locks.refusal(self.code)
        self.assertIn('بدهی', message)
        self.assertIn('اشغال معبر', message)
        self.assertIn(self.code, message)

    def test_codes_are_found_however_they_are_typed(self):
        from main.gis import locks
        self.lock()
        typed = self.code.replace('-', ' ')
        persian = typed.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
        for variant in (self.code, typed, persian, f' {self.code} ', self.code.replace('-', '_')):
            self.assertTrue(locks.locked_parcels(variant), variant)
        self.assertEqual(locks.locked_parcels('1-1-1-1-1-1'), [])
        self.assertEqual(locks.locked_parcels(''), [])

    def test_a_request_for_a_locked_plot_is_not_created(self):
        from main.models import ServiceRequest
        self.lock()
        self.submit(self.code)
        self.assertFalse(ServiceRequest.objects.filter(user=self.citizen).exists())

    def test_a_request_is_created_once_the_lock_is_released_or_for_another_plot(self):
        from django.utils import timezone
        from main.models import ServiceRequest
        lock = self.lock()
        self.submit('0-0-999-999-9')                       # some other plot: allowed
        self.assertEqual(ServiceRequest.objects.filter(user=self.citizen).count(), 1)
        lock.unlocked_at = timezone.now()
        lock.save()
        self.submit(self.code)
        self.assertEqual(ServiceRequest.objects.filter(user=self.citizen).count(), 2)
        self.assertEqual(ServiceRequest.objects.filter(user=self.citizen, parcel_number=self.code).count(), 1)

    def test_submit_refuses_a_locked_plot_whichever_door_is_used(self):
        from main import lifecycle
        from main.models import ServiceRequest
        self.lock()
        with self.assertRaises(lifecycle.TransitionError):
            lifecycle.submit(self.citizen, action='ثبت', request_type='other', title='t', description='d',
                             parcel_number=self.code)
        self.assertFalse(ServiceRequest.objects.exists())

    def test_the_permit_form_keeps_the_plot_it_was_given(self):
        from main.models import ServiceRequest
        from main.tests.test_permit_files import application
        isolate_private_media(self)
        response = client_for(self.citizen).post(reverse('main:construction_permit_request'), application(renewal_code=self.code))
        created = ServiceRequest.objects.filter(user=self.citizen, request_type='building_permit')
        self.assertEqual(created.count(), 1, response.status_code)
        self.assertEqual(created.get().parcel_number, self.code)       # the request now names the plot, so the lock can see it

    def test_the_permit_form_refuses_a_locked_plot(self):
        from main.models import ServiceRequest
        from main.tests.test_permit_files import application
        isolate_private_media(self)
        self.lock()
        client_for(self.citizen).post(reverse('main:construction_permit_request'), application(renewal_code=self.code))
        self.assertFalse(ServiceRequest.objects.filter(request_type='building_permit').exists())

    def test_staff_cannot_approve_a_request_for_a_locked_plot(self):
        from main import lifecycle
        from main.models import ServiceRequest
        request = ServiceRequest.objects.create(user=self.citizen, request_type='other', title='t', description='d',
                                                parcel_number=self.code, status='pending')
        engineer = make_user('engineer', **LOCAL)
        self.lock()
        with self.assertRaises(lifecycle.TransitionError):
            lifecycle.approve(request, engineer)
        with self.assertRaises(lifecycle.TransitionError):
            lifecycle.set_status(request, engineer, 'approved')
        request.refresh_from_db()
        self.assertEqual(request.status, 'pending')
        lifecycle.reject(request, engineer, 'بدهی')       # saying no is always allowed
        self.assertEqual(request.status, 'rejected')

    def test_approval_works_when_the_plot_is_not_locked(self):
        from main import lifecycle
        from main.models import ServiceRequest
        request = ServiceRequest.objects.create(user=self.citizen, request_type='other', title='t', description='d',
                                                parcel_number=self.code, status='pending')
        lifecycle.approve(request, make_user('engineer', **LOCAL))
        self.assertEqual(request.status, 'approved')

    def test_the_request_form_refuses_a_locked_plot(self):
        from main.forms import ServiceRequestForm
        self.lock()
        for form_class in (ServiceRequestForm,):
            form = form_class({'title': 't', 'description': 'd', 'parcel_number': self.code})
            form.is_valid()
            self.assertIn('parcel_number', form.errors, form_class.__name__)
            self.assertIn('قفل', form.errors['parcel_number'][0])


class HousingAreaIsNeighbourhoodSix(TestCase):
    def setUp(self):
        self.village = VillageMap.objects.get(slug=SLUG)
        self.housing = MapParcel.objects.filter(village_map=self.village, zone='6')

    def test_the_housing_plots_are_in_the_map(self):
        self.assertGreater(self.housing.count(), 800)
        self.assertEqual(MapZone.objects.get(village_map=self.village, number='6').parcel_count, self.housing.exclude(block_no='').count())

    def test_its_blocks_restart_at_one_and_do_not_clash_with_the_villages(self):
        from main.models import MapBlock
        housing = MapBlock.objects.filter(village_map=self.village, zone='6')
        self.assertEqual(housing.count(), 32)
        self.assertTrue(MapBlock.objects.filter(village_map=self.village, number='3').exclude(zone='6').exists())
        self.assertTrue(housing.filter(number='3').exists())              # block 3 exists twice, in different neighbourhoods

    def test_codes_and_uids_say_which_neighbourhood_they_are_in(self):
        coded = self.housing.exclude(renewal_code='')
        self.assertGreater(coded.count(), 500)
        for parcel in coded[:300]:
            self.assertTrue(parcel.renewal_code.endswith('-6'), parcel.renewal_code)
            self.assertTrue(parcel.uid.startswith('6:'), parcel.uid)
        self.assertEqual(MapParcel.objects.filter(village_map=self.village).values('uid').distinct().count(),
                         MapParcel.objects.filter(village_map=self.village).count())

    def test_permits_the_drawing_marks_and_the_subdivision_numbers(self):
        self.assertGreater(self.housing.filter(permit_in_drawing=True).count(), 150)
        self.assertGreater(self.housing.exclude(lot_no='').count(), 800)
        self.assertFalse(MapParcel.objects.exclude(zone='6').filter(permit_in_drawing=True).exists())

    @skipUnless(HAVE_SHAPELY, 'shapely is only needed to rebuild the map (scripts/gis/requirements.txt)')
    def test_no_housing_plot_overlaps_a_plot_of_the_village(self):
        from shapely.geometry import shape
        from shapely.strtree import STRtree
        village = [shape(p.geometry) for p in MapParcel.objects.filter(village_map=self.village, kind='drawn').exclude(zone='6')]
        tree = STRtree(village)
        bad = 0
        for plot in self.housing[:400]:
            geometry = shape(plot.geometry)
            bad += any(geometry.intersection(village[i]).area > 1 for i in tree.query(geometry))
        self.assertEqual(bad, 0)

    def test_the_panel_shows_the_lot_number_and_the_permit_mark(self):
        client = client_for(make_user('engineer', **LOCAL))
        parcel = self.housing.filter(permit_in_drawing=True).exclude(renewal_code='').first()
        detail = client.get(reverse('main:gis_parcel', args=[SLUG, parcel.pk])).json()['parcel']
        self.assertTrue(detail['permit_in_drawing'])
        self.assertEqual(detail['zone'], '6')
        self.assertEqual(detail['lot_no'], parcel.lot_no)


class LegendNames(TestCase):
    def names(self):
        return {c.key: c.name for c in LandUseClass.objects.filter(village_map__slug=SLUG)}

    def test_colours_take_the_names_the_plans_legend_gives_them(self):
        names = self.names()
        self.assertEqual(names['ffff00'], 'مسکونی')
        self.assertEqual(names['ff0000'], 'تجاری')
        self.assertEqual(names['004c4c'], 'مذهبی')
        self.assertEqual(names['7fffff'], 'آموزشی (دبستان)')
        self.assertEqual(names['999999'], 'اداری')
        self.assertEqual(names['00ff00'], 'فضای سبز عمومی')

    def test_a_colour_the_legend_does_not_list_stays_unnamed(self):
        self.assertEqual(self.names()['ffbf00'], '')

    def test_easements_carry_the_plans_own_wording(self):
        from main.gis import rules
        self.assertEqual(rules.label('qanat'), 'حریم کمی قنات')
        self.assertIn('۶ متر', rules.rule('qanat'))
        self.assertIn('پیلوت', rules.rule('defense1'))
        self.assertIn('پیلوت', rules.rule('defense2'))
        self.assertIn('ممنوع', rules.rule('quality'))
        self.assertEqual(rules.rule('general'), '')

    def test_a_plot_in_a_qanat_easement_is_shown_the_rule(self):
        client = client_for(make_user('engineer', **LOCAL))
        parcel = MapParcel.objects.exclude(easement_hits=[]).first()
        detail = client.get(reverse('main:gis_parcel', args=[SLUG, parcel.pk])).json()['parcel']
        self.assertTrue(all(e['label'] for e in detail['easements']))
        self.assertTrue(any(e['rule'] for e in detail['easements']))


class LandAndBuildingAreHalvesOfAProperty(TestCase):
    def setUp(self):
        self.parcel = MapParcel.objects.filter(village_map__slug=SLUG, building_count__gt=0).exclude(renewal_code='').first()
        self.client = client_for(make_user('engineer', **LOCAL))
        self.url = reverse('main:gis_archive_save', args=[SLUG, self.parcel.pk])

    def test_each_half_has_its_own_owner(self):
        response = post_json(self.client, self.url, {
            'owner_name': 'صاحب زمین', 'owner_national_id': '0123456789',
            'building_owner_name': 'صاحب ساختمان', 'building_owner_national_id': '۱۲۳۴۵۶۷۸۹۰', 'building_owner_phone': '09151234567',
            'building_floors': '۲', 'building_floor_area': '186.5'})
        self.assertEqual(response.status_code, 200, response.content)
        archive = ParcelArchive.objects.get(parcel=self.parcel)
        self.assertEqual((archive.owner_name, archive.building_owner_name), ('صاحب زمین', 'صاحب ساختمان'))
        self.assertEqual((archive.building_owner_national_id, archive.building_floors, archive.building_floor_area),
                         ('1234567890', 2, 186.5))
        shown = response.json()['parcel']['archive']
        self.assertEqual((shown['building_owner_name'], shown['building_floors'], shown['building_floor_area']), ('صاحب ساختمان', 2, 186.5))

    def test_bad_building_values_are_refused(self):
        for body in ({'building_owner_national_id': '12'}, {'building_floors': '0'}, {'building_floors': 'دو'},
                     {'building_floors': '500'}, {'building_floor_area': 'x'}, {'building_floor_area': '-5'},
                     {'building_owner_phone': '09x'}, {'building_owner_name': 'x' * 200}):
            with self.subTest(body=body):
                self.assertEqual(post_json(self.client, self.url, body).status_code, 400)
        self.assertFalse(ParcelArchive.objects.exists())

    def test_the_plot_shows_both_areas(self):
        detail = self.client.get(reverse('main:gis_parcel', args=[SLUG, self.parcel.pk])).json()['parcel']
        self.assertGreater(detail['area'], 0)
        self.assertGreater(detail['building_area'], 0)
        self.assertEqual(detail['building_count'], self.parcel.building_count)

    def test_clicking_a_building_can_find_its_plot(self):
        buildings = self.client.get(reverse('main:gis_buildings', args=[SLUG])).json()['features']
        owned = [b for b in buildings if b['properties']['p']]
        self.assertGreater(len(owned), 3000)
        self.assertTrue(MapParcel.objects.filter(pk=owned[0]['properties']['p']).exists())

    def test_the_page_has_a_tick_for_land_and_one_for_buildings_and_for_zones(self):
        page = self.client.get(reverse('main:gis_map', args=[SLUG]))
        for marker in ('data-layer="plots"', 'data-layer="buildings"', 'data-layer="zones"', 'id="vm-filter"', 'data-pane="building"'):
            self.assertContains(page, marker)
        self.assertNotContains(page, 'vm-chip')                  # the status chips no longer sit on the map


@skipUnless(HAVE_SHAPELY, 'shapely is only needed to rebuild the map from a drawing (scripts/gis/requirements.txt)')
class HousingAreaHelpers(TestCase):
    def test_touching_plots_form_one_block_named_by_the_label_inside(self):
        from shapely.geometry import Point, box
        from scripts.gis.housing_area import group_blocks
        lots = [box(0, 0, 10, 10), box(10, 0, 20, 10), box(20, 0, 30, 10), box(100, 0, 110, 10)]
        group_of, names, _ = group_blocks(lots, [(Point(15, 5), '7'), (Point(105, 5), '9')])
        self.assertEqual(len({group_of[0], group_of[1], group_of[2]}), 1)
        self.assertNotEqual(group_of[0], group_of[3])
        self.assertEqual([names[g] for g in group_of], ['7', '7', '7', '9'])

    def test_a_group_without_a_label_takes_the_nearest_labelled_one_if_close(self):
        from shapely.geometry import Point, box
        from scripts.gis.housing_area import group_blocks
        lots = [box(0, 0, 10, 10), box(60, 0, 70, 10), box(1000, 0, 1010, 10)]
        group_of, names, _ = group_blocks(lots, [(Point(5, 5), '3')])
        self.assertEqual(names[group_of[0]], '3')
        self.assertEqual(names[group_of[1]], '3')           # 55 m away: close enough
        self.assertEqual(names[group_of[2]], '')            # 1 km away: no block

    def test_the_label_nearest_the_centre_wins(self):
        from shapely.geometry import Point, box
        from scripts.gis.housing_area import nearest_inside
        lot = box(0, 0, 10, 10)
        self.assertEqual(nearest_inside(lot, [(Point(1, 1), 'edge'), (Point(5, 5), 'middle'), (Point(50, 5), 'outside')]), 'middle')
        self.assertIsNone(nearest_inside(lot, [(Point(50, 5), 'outside')]))

    def test_the_legends_numbers_name_the_hatch_layers(self):
        from scripts.gis.build_village_map import land_use_name
        self.assertEqual(land_use_name('1p'), 'مسکونی')
        self.assertEqual(land_use_name('2 hp'), 'تجاری')
        self.assertEqual(land_use_name('27hp'), 'جهانگردی و پذیرایی')
        self.assertEqual(land_use_name('50 p'), '')                   # not in the legend
        self.assertEqual(land_use_name('hp'), '')


class MapDetails(TestCase):
    """Roads, water, power, trees, limits and street names around the plots (from the 1405 detail drawing)."""

    def url(self):
        return reverse('main:gis_context', args=[SLUG])

    def test_engineer_gets_the_surroundings(self):
        body = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()
        self.assertEqual(body['type'], 'FeatureCollection')
        groups = {f['properties']['g'] for f in body['features']}
        self.assertEqual(groups, {'roads', 'water', 'power', 'trees', 'limits', 'signs', 'names'})
        self.assertGreater(len(body['features']), 4000)

    def test_everything_lies_in_the_village(self):
        features = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()['features']
        for f in features:
            first = f['geometry']['coordinates']
            while isinstance(first[0], list):
                first = first[0]
            self.assertTrue(59.2 < first[0] < 59.4 and 32.85 < first[1] < 32.97, f['properties'])

    def test_street_names_are_readable_persian(self):
        names = [f['properties']['name'] for f in client_for(make_user('engineer', **LOCAL)).get(self.url()).json()['features']
                 if f['properties']['g'] == 'names']
        self.assertTrue(names)
        self.assertTrue(any('امام خمینی' in n for n in names))
        self.assertTrue(all(re.search('[؀-ۿ]', n) for n in names))

    def test_closed_to_everyone_else(self):
        for who in (make_user('citizen'), make_user('engineer', province='خراسان جنوبی', county='بیرجند', city_village='ولدآباد')):
            self.assertIn(client_for(who).get(self.url()).status_code, (302, 403))
        self.assertEqual(client_for().get(self.url()).status_code in (302, 401, 403), True)

    def test_page_has_the_detail_tick_boxes(self):
        page = client_for(make_user('engineer', **LOCAL)).get(reverse('main:gis_map', args=[SLUG]))
        for group in ('roads', 'water', 'power', 'trees', 'limits', 'signs', 'names'):
            self.assertContains(page, f'data-detail="{group}"')


class BuildingsMatchTheDrawing(TestCase):
    def test_every_building_is_a_polygon_and_plot_counts_add_up(self):
        import json as _json
        from main.gis.loader import DATA_DIR
        data = _json.loads((DATA_DIR / 'dastgerd.geojson').read_text(encoding='utf-8'))
        buildings = [f for f in data['features'] if f['properties']['type'] == 'building']
        self.assertGreater(len(buildings), 3700)
        self.assertTrue(all(f['geometry']['type'] == 'Polygon' for f in buildings))
        on_plots = sum(1 for f in buildings if f['properties']['parcel'])
        counted = sum(f['properties'].get('bld_count', 0) for f in data['features'] if f['properties']['type'] == 'parcel')
        self.assertEqual(on_plots, counted)


class MapPlanLayer(TestCase):
    """The plan as drawn in AutoCAD: the map's default base layer."""

    def url(self):
        return reverse('main:gis_cad', args=[SLUG])

    def test_engineer_gets_areas_lines_and_texts_with_the_drawings_colours(self):
        body = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()
        kinds = {item['k'] for item in body['items']}
        self.assertEqual(kinds, {'h', 'l', 't'})
        self.assertGreater(len(body['items']), 15000)
        self.assertTrue(all(re.fullmatch(r'#[0-9a-f]{6}', layer['c']) for layer in body['layers']))
        patterns = {item.get('p') for item in body['items'] if item['k'] == 'h'}
        self.assertTrue({None, 'l'} <= patterns)                  # solid fills and hatched areas

    def test_every_text_is_readable_persian_or_a_number(self):
        items = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()['items']
        texts = [item['s'] for item in items if item['k'] == 't']
        self.assertGreater(len(texts), 300)
        for text in texts:
            self.assertTrue(re.search('[\u0600-\u06FF]', text) or re.fullmatch(r'[\d\s./:+\-()%]+', text), text)
            self.assertNotIn('<', text)

    def test_everything_lies_in_the_village(self):
        items = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()['items']
        for item in items[:: max(1, len(items) // 800)]:
            first = item['r'][0] if item['k'] == 'h' else item['p'] if item['k'] == 'l' else [item['x'], item['y']]
            self.assertTrue(59.2 < first[0] < 59.4 and 32.85 < first[1] < 32.97, item)

    def test_closed_to_everyone_else(self):
        for who in (make_user('citizen'), make_user('engineer', province='خراسان جنوبی', county='بیرجند', city_village='ولدآباد')):
            self.assertIn(client_for(who).get(self.url()).status_code, (302, 403))
        self.assertIn(client_for().get(self.url()).status_code, (302, 401, 403))

    def test_page_offers_the_plan_as_the_default_base(self):
        page = client_for(make_user('engineer', **LOCAL)).get(reverse('main:gis_map', args=[SLUG]))
        self.assertContains(page, 'name="basemap" value="cad" checked')
        self.assertContains(page, 'village-cad.js')

    def test_the_plans_legend_is_a_list_of_toggles(self):
        body = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()
        rows = body['legend']
        self.assertGreater(len(rows), 30)
        labels = [r['t'] for r in rows]
        for expected in ('مسکونی', 'مذهبی', 'تجاری', 'فضای سبز', 'مسیل', 'باغ', 'زراعت'):
            self.assertTrue(any(expected in label for label in labels), expected)
        layer_names = {layer['n'] for layer in body['layers']}
        for row in rows:
            for key in row['l']:
                self.assertIn(key.split('|')[0], layer_names, key)       # every toggle points at a layer of the plan

    def test_the_sheets_title_block_is_not_on_the_map(self):
        body = client_for(make_user('engineer', **LOCAL)).get(self.url()).json()
        texts = ' '.join(item['s'] for item in body['items'] if item['k'] == 't')
        for word in ('انقلاب اسلامی', 'معاونت عمران', 'مهندسین مشاور', 'مقیاس', 'طرح هادی بازنگری', 'موجود پیشنهادی'):
            self.assertNotIn(word, texts, word)
        xs = [item['x'] for item in body['items'] if item['k'] == 't']
        self.assertGreater(min(xs), 59.27)                       # nothing from the sheet's left column (logo, legend)

    def test_page_has_the_legend_box_and_the_xy_search(self):
        page = client_for(make_user('engineer', **LOCAL)).get(reverse('main:gis_map', args=[SLUG]))
        for marker in ('id="vm-plan-legend"', 'id="vm-xy"', 'id="vm-x"', 'id="vm-y"'):
            self.assertContains(page, marker)


class MapBackgroundsAndTimeline(TestCase):
    def setUp(self):
        self.page = client_for(make_user('engineer', **LOCAL)).get(reverse('main:gis_map', args=[SLUG]))

    def config(self):
        return json.loads(re.search(r'<script id="vm-config" type="application/json">(.*?)</script>', self.page.content.decode(), re.S).group(1))

    def test_timeline_runs_from_1370_to_this_year(self):
        years = self.config()['years']
        self.assertEqual(years[0], 1370)
        self.assertEqual(years, list(range(1370, years[-1] + 1)))
        self.assertContains(self.page, 'min="1370"')

    def test_satellite_is_first_with_the_street_map_next_to_it(self):
        maps = self.config()['basemaps']
        self.assertEqual([m['id'] for m in maps][:2], ['satellite', 'osm'])
        self.assertTrue(all(m['maxZoom'] >= m['nativeZoom'] for m in maps))      # zooming past the last real tile stretches it

    def test_a_village_with_stored_imagery_serves_it_from_its_own_server(self):
        satellite = self.config()['basemaps'][0]
        self.assertEqual(satellite['url'], f'/gis/{SLUG}/tiles/satellite/{{z}}/{{x}}/{{y}}.jpg')
        self.assertFalse(satellite['wayback'])                                      # the dated releases live on a server Iran cannot reach

    def test_without_stored_imagery_the_foreign_provider_and_its_timeline_stay(self):
        with mock.patch('main.gis.tiles.available', return_value=False):
            page = client_for(make_user('engineer', **LOCAL)).get(reverse('main:gis_map', args=[SLUG]))
        config = json.loads(re.search(r'<script id="vm-config" type="application/json">(.*?)</script>', page.content.decode(), re.S).group(1))
        self.assertTrue(config['basemaps'][0]['wayback'])
        self.assertTrue(config['waybackConfig'].startswith('https://'))

    def test_the_drawing_layers_urls_change_with_the_file(self):
        urls = self.config()['urls']
        self.assertRegex(urls['cad'], r'/cad/\?v=\d+$')
        self.assertRegex(urls['context'], r'/context/\?v=\d+$')

    def test_page_can_hide_the_archive_panel_and_shows_the_imagery_note(self):
        self.assertContains(self.page, 'id="vm-side-toggle"')
        self.assertContains(self.page, 'id="vm-imagery"')


class PlanHasNoFrame(TestCase):
    def test_no_grid_numbers_or_frame_texts(self):
        items = client_for(make_user('engineer', **LOCAL)).get(reverse('main:gis_cad', args=[SLUG])).json()['items']
        numbers = [i['s'] for i in items if i['k'] == 't' and re.fullmatch(r'\d{6,7}', i['s'])]
        self.assertEqual(numbers, [])                              # 3645800, 713200 ... of the sheet's coordinate grid


class TheThreeStaffOfTheVillageSeeTheMapInTheirPanels(TestCase):
    """The technical expert, the administrative expert and the dehyari of a village each find the map in their own panel; staff of another village do not."""
    PANELS = {'engineer': 'main:dehyari_expert_dashboard', 'clerk': 'main:clerk_dashboard', 'dehyari': 'main:dehyari_dashboard'}

    def test_each_role_has_the_link_in_its_panel(self):
        link = reverse('main:gis_map', args=[SLUG])
        for role, panel in self.PANELS.items():
            with self.subTest(role=role):
                page = client_for(make_user(role, **LOCAL)).get(reverse(panel))
                self.assertContains(page, link)

    def test_staff_of_another_village_do_not_get_the_link(self):
        link = reverse('main:gis_map', args=[SLUG])
        for role, panel in self.PANELS.items():
            with self.subTest(role=role):
                page = client_for(make_user(role, province='خراسان جنوبی', county='بیرجند', city_village='ولدآباد')).get(reverse(panel))
                self.assertNotContains(page, link)

    def test_a_dehyari_whose_profile_names_no_village_gets_it_through_the_municipality(self):
        from main.tests.helpers import make_municipality
        dehyari = make_user('dehyari')
        make_municipality(dehyari, 'دستگرد').__class__.objects.filter(admin_user=dehyari).update(county='بیرجند')
        link = reverse('main:gis_map', args=[SLUG])
        self.assertContains(client_for(dehyari).get(reverse('main:dehyari_dashboard')), link)
        self.assertEqual(client_for(dehyari).get(link).status_code, 200)
