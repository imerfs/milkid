"""Building permit, step 2: reading the shamim (AutoCAD) file, the plot's limits, forms 1 and 2, handing them over."""
import io
import json
import zipfile

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main.models import MapParcel, Notification, PermitFile, VillageMap
from main.office import geo, permit_step2, plotmap, shamim
from main.tests.helpers import client_for, isolate_private_media, make_municipality, make_user, requires_gis_data
from main.tests.shamim_helpers import shamim_dxf
from main.tests.test_permit_files import application, national_id, upload

SLUG = 'dastgerd'


def village_name():
    return VillageMap.objects.get(slug=SLUG).name           # the applicant's village is the map's, so the shamim finds it


def plot(code='0-0-8-182-2'):
    return MapParcel.objects.filter(village_map__slug=SLUG, renewal_code=code).first()


class Geometry(SimpleTestCase):
    def test_utm_matches_what_the_map_page_shows(self):
        lat, lng = geo.utm_to_latlng(714399, 3645474)
        self.assertAlmostEqual(lat, 32.926524, places=4)
        self.assertAlmostEqual(lng, 59.292955, places=4)

    def test_utm_round_trip(self):
        x, y = geo.latlng_to_utm(32.9265, 59.2929)
        lat, lng = geo.utm_to_latlng(x, y)
        self.assertAlmostEqual(lat, 32.9265, places=7)
        self.assertAlmostEqual(lng, 59.2929, places=7)

    def test_square_area_centroid_and_sides(self):
        ring = [(0, 0), (10, 0), (10, 20), (0, 20)]
        self.assertEqual(geo.area(ring), 200)
        self.assertEqual(geo.centroid(ring), (5, 10))
        sides = {e['side']: e['length'] for e in geo.edges(ring)}
        self.assertEqual(sides, {'south': 10, 'east': 20, 'north': 10, 'west': 20})
        self.assertEqual({e['side']: e['length'] for e in geo.edges(ring[::-1])}, sides)       # either winding
        self.assertTrue(geo.contains(ring, 3, 3))
        self.assertFalse(geo.contains(ring, 30, 3))


@requires_gis_data
class ReadingTheShamim(TestCase):
    def setUp(self):
        self.parcel = plot()
        self.map = VillageMap.objects.get(slug=SLUG)

    def test_the_outline_is_found_and_laid_on_the_map(self):
        info = shamim.analyse('plot.dxf', shamim_dxf(self.parcel), declared_area=self.parcel.area_m2, village_map=self.map)
        self.assertTrue(info['ok'], info)
        self.assertAlmostEqual(info['area'], self.parcel.area_m2, delta=self.parcel.area_m2 * 0.03)
        self.assertEqual(info['georef'], 'utm')
        self.assertEqual(info['matches'][0]['parcel_id'], self.parcel.pk)
        self.assertEqual(info['matches'][0]['code'], self.parcel.renewal_code)
        self.assertTrue(info['outline'])
        self.assertEqual(info['notes'], [])

    def test_the_outline_closest_to_the_declared_area_is_the_plot(self):
        info = shamim.analyse('plot.dxf', shamim_dxf(self.parcel), declared_area=self.parcel.area_m2, village_map=self.map)
        self.assertLess(info['area'], 1000)                                  # not the 200 x 200 m shape drawn beside it

    def test_a_different_declared_area_is_pointed_out(self):
        info = shamim.analyse('plot.dxf', shamim_dxf(self.parcel), declared_area=self.parcel.area_m2 * 2, village_map=self.map)
        self.assertTrue(any('فرق دارد' in note for note in info['notes']))

    def test_other_formats(self):
        ring = [list(p) for p in self.parcel.geometry['coordinates'][0]]
        collection = json.dumps({'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {},
                                                                              'geometry': {'type': 'Polygon', 'coordinates': [ring]}}]}).encode()
        self.assertEqual(shamim.analyse('p.geojson', collection, village_map=self.map)['matches'][0]['parcel_id'], self.parcel.pk)
        kml = ('<kml><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>' +
               ' '.join(f'{x},{y},0' for x, y in ring) + '</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>').encode()
        self.assertEqual(shamim.analyse('p.kml', kml, village_map=self.map)['matches'][0]['parcel_id'], self.parcel.pk)
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, 'w') as archive:
            archive.writestr('sub/plot.dxf', shamim_dxf(self.parcel))
        self.assertTrue(shamim.analyse('plot.zip', packed.getvalue(), village_map=self.map)['ok'])

    def test_a_dwg_is_explained_not_guessed(self):
        info = shamim.analyse('plot.dwg', b'AC1032' + b'\x00' * 50, village_map=self.map)
        self.assertFalse(info['ok'])
        self.assertIn('DXF', info['notes'][0])

    def test_damaged_and_empty_files_give_a_note_not_an_error(self):
        for name, data in (('x.dxf', b'garbage'), ('x.geojson', b'{'), ('x.zip', b'PK'), ('x.dxf', b''), ('x.txt', b'a')):
            info = shamim.analyse(name, data, village_map=self.map)
            self.assertFalse(info['ok'], name)
            self.assertTrue(info['notes'], name)

    def test_a_zip_holding_nothing_readable(self):
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, 'w') as archive:
            archive.writestr('notes.txt', 'hello')
        self.assertFalse(shamim.analyse('x.zip', packed.getvalue())['ok'])

    def test_a_drawing_in_its_own_coordinates_is_measured_but_not_placed(self):
        import ezdxf
        doc = ezdxf.new()
        doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 20), (0, 20)], close=True)
        buffer = io.StringIO()
        doc.write(buffer)
        info = shamim.analyse('x.dxf', buffer.getvalue().encode(), declared_area=200, village_map=self.map)
        self.assertEqual((info['ok'], info['area'], info['georef'], info['matches']), (True, 200.0, 'local', []))
        self.assertTrue(any('نیفتاد' in n or 'جور نیست' in n for n in info['notes']))


@requires_gis_data
class PlotLimits(TestCase):
    def test_the_four_sides_are_measured_and_named(self):
        village_map = VillageMap.objects.get(slug=SLUG)
        limits = plotmap.limits(village_map, parcel_id=plot().pk)
        self.assertEqual(set(limits), {'north', 'south', 'west', 'east'})
        self.assertTrue(all(side['length'] > 0 and side['to'] for side in limits.values()), limits)
        self.assertTrue(any(side['to'].startswith('قطعه') or side['to'] == 'ملک' for side in limits.values()))

    def test_the_sheet_holds_the_plot_the_neighbours_and_the_edge_lengths(self):
        village_map = VillageMap.objects.get(slug=SLUG)
        sheet = plotmap.sheet(village_map, parcel_id=plot().pk)
        self.assertGreaterEqual(len(sheet['plot']), 3)
        self.assertTrue(sheet['neighbours'])
        self.assertEqual(len(sheet['edges']), len(sheet['plot']))
        self.assertAlmostEqual(sheet['area'], plot().area_m2, delta=plot().area_m2 * 0.05)


class Village(TestCase):
    def setUp(self):
        isolate_private_media(self)
        self.parcel = plot()
        self.village = village_name()
        self.dehyari = make_user('dehyari', city_village=self.village)
        make_municipality(self.dehyari, self.village)
        self.clerk = make_user('clerk', city_village=self.village)
        self.citizen = make_user('citizen', city_village=self.village)
        self.neighbour = make_user('citizen', city_village=self.village)
        self.stranger = make_user('clerk', city_village='روستای دیگر')
        for name in ('dehyari', 'clerk', 'citizen', 'neighbour', 'stranger'):
            setattr(self, name, User.objects.get(pk=getattr(self, name).pk))
        post = application('bonyad', area=str(round(self.parcel.area_m2, 2)), lot_number='233', shamim=upload('plot.dxf', shamim_dxf(self.parcel)))
        client_for(self.citizen).post(reverse('main:building_permit_form'), post)
        self.permit = PermitFile.objects.get()

    def open(self):
        client_for(self.clerk).post(reverse('main:permit_open', args=[self.permit.pk]), {'renewal_code': self.parcel.renewal_code})
        self.permit.refresh_from_db()

    def forms(self, who, **extra):
        return client_for(who).get(reverse('main:permit_forms', args=[self.permit.pk]), extra)

    def form1(self, who=None, **change):
        data = {'number': '18/1835', 'date': '1405/08/04', 'request_no': '18/1836', 'request_date': '1405/08/04', 'name': 'علی رضایی',
                'north_length': '10', 'north_to': 'معبر', 'south_length': '10', 'south_to': 'قطعه ۲۳۷', 'west_length': '20', 'west_to': 'ملک',
                'east_length': '20', 'east_to': 'ملک', **change}
        return client_for(who or self.clerk).post(reverse('main:permit_form1_save', args=[self.permit.pk]), data)

    def form2(self, who=None, **change):
        data = {'name': 'علی رضایی', 'father': 'حسن', 'village': 'دستگرد', 'purpose': 'construction', 'attach1': 'on', 'attach2': 'on', **change}
        return client_for(who or self.citizen).post(reverse('main:permit_form2_save', args=[self.permit.pk]), data)


@requires_gis_data
class ShamimAtFiling(Village):
    def test_the_file_is_read_when_it_arrives(self):
        info = self.permit.shamim_info
        self.assertTrue(info['ok'])
        self.assertEqual(info['matches'][0]['code'], self.parcel.renewal_code)

    def test_the_clerk_is_offered_the_plot_under_the_outline_first(self):
        choices = permit_step2.parcel_choices(self.permit)
        self.assertEqual((choices[0]['id'], choices[0]['source']), (self.parcel.pk, 'shamim'))
        page = client_for(self.clerk).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn('بررسی خودکار فایل شمیم', page)
        self.assertIn(f'data-code="{self.parcel.renewal_code}"', page)

    def test_it_can_be_read_again(self):
        PermitFile.objects.filter(pk=self.permit.pk).update(shamim_info={})
        client_for(self.clerk).post(reverse('main:permit_shamim', args=[self.permit.pk]))
        self.permit.refresh_from_db()
        self.assertTrue(self.permit.shamim_info['ok'])
        client_for(self.citizen).post(reverse('main:permit_shamim', args=[self.permit.pk]))        # not theirs to do
        self.assertEqual(client_for(self.neighbour).post(reverse('main:permit_shamim', args=[self.permit.pk])).status_code, 302)


@requires_gis_data
class TheForms(Village):
    def test_forms_wait_for_the_file_to_be_opened(self):
        self.assertEqual(self.forms(self.clerk).status_code, 302)
        self.open()
        self.assertEqual(self.forms(self.clerk).status_code, 200)

    def test_only_the_owner_and_the_villages_staff_see_them(self):
        self.open()
        self.assertEqual(self.forms(self.citizen).status_code, 200)
        for who in (self.neighbour, self.stranger):
            self.assertEqual(self.forms(who).status_code, 404, who.profile.role)

    def test_the_page_carries_everything_it_draws(self):
        self.open()
        response = self.forms(self.clerk)
        payload = response.context['payload']
        self.assertTrue(payload['sheet']['plot'])
        self.assertEqual(set(payload['form1']['limits']), {'north', 'south', 'west', 'east'})
        self.assertTrue(all(side['length'] > 0 for side in payload['form1']['limits'].values()))
        self.assertEqual(payload['form1']['name'], 'علی رضایی')
        self.assertEqual(payload['form2']['ownership'], 'bonyad')
        self.assertEqual(payload['form2']['lessor'], 'بنیاد مسکن انقلاب اسلامی')
        self.assertEqual(payload['renewal_code'], self.parcel.renewal_code)
        for blank in payload['blank'].values():
            self.assertTrue(finders.find(blank.replace('/static/', '', 1)), blank)

    def test_the_staff_fill_form_one_and_the_owner_is_told(self):
        self.open()
        self.form1()
        self.permit.refresh_from_db()
        self.assertIsNotNone(self.permit.form1_at)
        self.assertEqual(self.permit.step2['form1']['limits']['north'], {'length': 10.0, 'to': 'معبر'})
        self.assertEqual(self.permit.step2['form2']['number'], '18/1836')            # the owner's request is registered under it
        self.assertTrue(Notification.objects.filter(user=self.citizen, title__contains='فرم ۱').exists())
        self.assertEqual(self.forms(self.citizen).context['payload']['form1']['number'], '18/1835')

    def test_form_one_needs_its_number_and_date_and_belongs_to_the_staff(self):
        self.open()
        self.form1(number='')
        self.assertIsNone(PermitFile.objects.get(pk=self.permit.pk).form1_at)
        self.form1(self.citizen)
        self.form1(self.neighbour)
        self.form1(self.stranger)
        self.assertIsNone(PermitFile.objects.get(pk=self.permit.pk).form1_at)

    def test_the_owner_fills_form_two_but_not_its_number(self):
        self.open()
        self.form1()
        self.form2(number='999', father='حسن', plot='562', attach3='on')
        self.permit.refresh_from_db()
        saved = self.permit.step2['form2']
        self.assertIsNotNone(self.permit.form2_at)
        self.assertEqual((saved['number'], saved['father'], saved['plot'], saved['attach3'], saved['attach4']), ('18/1836', 'حسن', '562', True, False))

    def test_form_two_belongs_to_the_owner(self):
        self.open()
        for who in (self.clerk, self.neighbour, self.stranger):
            self.form2(who)
        self.assertIsNone(PermitFile.objects.get(pk=self.permit.pk).form2_at)
        self.form2(father='')
        self.assertIsNone(PermitFile.objects.get(pk=self.permit.pk).form2_at)

    def test_nothing_is_saved_before_the_file_is_opened(self):
        self.form1()
        self.form2()
        self.permit.refresh_from_db()
        self.assertEqual((self.permit.form1_at, self.permit.form2_at), (None, None))

    def test_handing_over_needs_both_forms_and_moves_to_step_three(self):
        self.open()
        deliver = lambda who=self.clerk: client_for(who).post(reverse('main:permit_deliver', args=[self.permit.pk]))
        deliver()
        self.assertEqual(PermitFile.objects.get(pk=self.permit.pk).stage_no, 2)
        self.form1()
        deliver()
        self.assertEqual(PermitFile.objects.get(pk=self.permit.pk).stage_no, 2)
        self.form2()
        deliver(self.citizen)
        self.assertEqual(PermitFile.objects.get(pk=self.permit.pk).stage_no, 2)         # not the owner's to say
        deliver()
        self.permit.refresh_from_db()
        self.assertEqual((self.permit.stage_no, bool(self.permit.delivered_at)), (3, True))
        self.assertTrue(any('پایان مرحله ۲' in h['action'] for h in self.permit.request.workflow_history))
        self.form1(number='1/1')
        self.assertEqual(PermitFile.objects.get(pk=self.permit.pk).step2['form1']['number'], '18/1835')      # closed

    def test_numbers_continue_the_villages_own_pattern(self):
        self.open()
        self.form1(number='18/1835', request_no='18/1836')
        self.assertEqual(permit_step2._next_number(self.village), '18/1837')              # pylint: disable=protected-access

    def test_the_request_page_of_a_permit_leads_to_its_file(self):
        response = client_for(self.citizen).get(reverse('main:request_detail', args=[self.permit.request_id]))
        self.assertRedirects(response, reverse('main:permit_file', args=[self.permit.pk]), fetch_redirect_response=False)

    def test_the_file_page_links_to_the_forms_once_open(self):
        url = reverse('main:permit_forms', args=[self.permit.pk])
        self.assertNotIn(url, client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode())
        self.open()
        self.assertIn(url, client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode())
