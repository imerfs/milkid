"""Building-permit file, step 1 (افتتاح پرونده): filing, who sees it, opening it, and what it writes on the map."""
import os

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main.models import (MapParcel, Notification, ParcelArchive, ParcelLock, PermitDocument, PermitFile, ServiceRequest,
                         UserProfile, VillageMap)
from main.tests.helpers import client_for, isolate_private_media, make_municipality, make_user

VILLAGE, OTHER = 'روستای نمونه', 'روستای دیگر'
def _png():
    """A real one-pixel PNG: the upload guard checks the content, not only the name."""
    import struct
    import zlib

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


PNG = _png()
PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
DXF = b'0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n'


def national_id(seed):
    """A well-formed Iranian national code (the checksum digit is computed)."""
    nine = f'{seed:09d}'
    s = sum(int(nine[i]) * (10 - i) for i in range(9)) % 11
    return nine + str(s if s < 2 else 11 - s)


def upload(name='a.png', content=PNG):
    return SimpleUploadedFile(name, content)


def application(ownership='deed', **override):
    """The posted data of a valid application."""
    data = {
        'first_name': 'علی', 'last_name': 'رضایی', 'father_name': 'حسن', 'national_id': national_id(123456789),
        'id_number': '٤٥٦', 'birth_date': '۱۳۷۶/۰۳/۱۷', 'birth_place': 'قاین', 'phone': '09121234567',
        'area': '199.76', 'land_use': 'residential', 'address': 'دستگرد، کوچه‌ی ۱۲', 'permit_kind': 'construction',
        'ownership_type': ownership, 'lot_number': '233', 'doc_number': '10/3172', 'doc_date': '1404/03/05',
        'share_dang': '6', 'confirm': 'on',
        'birth_cert': [upload('b1.png'), upload('b2.png')], 'national_card': [upload('n1.png'), upload('n2.png')],
        'shamim': upload('plot.dxf', DXF),
    }
    data[{'deed': 'deed', 'agreement': 'agreement', 'bonyad': 'bonyad_contract'}[ownership]] = upload('paper.pdf', PDF)
    data.update(override)
    return {k: v for k, v in data.items() if v is not None}


class Village(TestCase):
    def setUp(self):
        isolate_private_media(self)
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        make_municipality(self.dehyari, VILLAGE)
        self.clerk = make_user('clerk', city_village=VILLAGE)
        self.engineer = make_user('engineer', city_village=VILLAGE)
        self.accountant = make_user('accountant', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE, father_name='حسن')
        self.neighbour = make_user('citizen', city_village=VILLAGE)
        self.stranger_clerk = make_user('clerk', city_village=OTHER)
        # make_user updates the profile row behind the cached object; reload so direct calls see the real role
        for name in ('dehyari', 'clerk', 'engineer', 'accountant', 'citizen', 'neighbour', 'stranger_clerk'):
            setattr(self, name, User.objects.get(pk=getattr(self, name).pk))

    def file(self, who=None, ownership='deed', **override):
        response = client_for(who or self.citizen).post(reverse('main:building_permit_form'), application(ownership, **override))
        return response

    def filed(self, **kwargs):
        response = self.file(**kwargs)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['errors'])
        return PermitFile.objects.latest('pk')


class Filing(Village):
    def test_the_form_opens_filled_with_what_the_site_knows(self):
        UserProfile.objects.filter(user=self.citizen).update(national_id=national_id(555), mobile_number='09129999999')
        self.citizen.first_name, self.citizen.last_name = 'مریم', 'احمدی'
        self.citizen.save()
        page = client_for(self.citizen).get(reverse('main:building_permit_form')).content.decode()
        for value in ('مریم', 'احمدی', 'حسن', national_id(555), '09129999999'):
            self.assertIn(f'value="{value}"', page)

    def test_only_citizens_file(self):
        for who in (self.clerk, self.engineer):
            self.assertEqual(client_for(who).get(reverse('main:building_permit_form')).status_code, 302)
        self.assertEqual(self.client.get(reverse('main:building_permit_form')).status_code, 302)

    def test_a_valid_application_makes_the_request_the_file_the_people_and_the_papers(self):
        permit = self.filed()
        sr = permit.request
        self.assertEqual((sr.request_type, sr.user, sr.status, sr.workflow_stage), ('building_permit', self.citizen, 'pending', 'expert_review'))
        self.assertEqual((permit.stage_no, permit.state, permit.ownership_type, permit.lot_number), (1, 'submitted', 'deed', '233'))
        self.assertEqual(str(permit.area_m2), '199.76')
        person = permit.people.get()
        self.assertEqual((person.role, person.user, person.national_id, person.birth_date), ('applicant', self.citizen, national_id(123456789), '1376/03/17'))
        kinds = sorted(permit.documents.values_list('kind', flat=True))
        self.assertEqual(kinds, ['birth_cert', 'birth_cert', 'deed', 'national_card', 'national_card', 'shamim'])
        self.assertEqual(sr.city_village_id, None)           # no geography chosen: the profile's village is what counts
        self.assertEqual(sr.property_usage, 'مسکونی')

    def test_identity_papers_are_kept_outside_media(self):
        from django.conf import settings
        permit = self.filed()
        for doc in permit.documents.all():
            self.assertTrue(os.path.abspath(doc.document.path).startswith(os.path.abspath(settings.PRIVATE_MEDIA_ROOT)))
            self.assertNotIn(doc.original_name, doc.document.name)      # a random name, not the user's

    def test_what_was_typed_stays_in_the_profile_for_the_next_time(self):
        self.filed()
        profile = UserProfile.objects.get(user=self.citizen)
        self.assertEqual((profile.father_name, profile.id_number, profile.birth_date, profile.birth_place),
                         ('حسن', '456', '1376/03/17', 'قاین'))
        self.assertEqual(User.objects.get(pk=self.citizen.pk).first_name, 'علی')
        self.assertEqual(profile.national_id, national_id(123456789))
        page = client_for(self.citizen).get(reverse('main:building_permit_form')).content.decode()
        self.assertIn('value="قاین"', page)

    def test_the_village_staff_are_told(self):
        permit = self.filed()
        for who in (self.clerk, self.engineer, self.dehyari):
            self.assertTrue(Notification.objects.filter(user=who, related_request=permit.request).exists(), who.profile.role)
        self.assertFalse(Notification.objects.filter(user=self.accountant).exists())

    def test_a_bonyad_contract_and_its_numbers_are_kept(self):
        permit = self.filed(ownership='bonyad', project_code='29033111133395', lease_years='2', limit_north='معبر ۱۲ متری')
        self.assertEqual((permit.ownership_type, permit.project_code, permit.details['lease_years']), ('bonyad', '29033111133395', '2'))
        self.assertTrue(permit.documents.filter(kind='bonyad_contract').exists())

    def test_other_owners_come_with_their_own_papers(self):
        permit = self.filed(co1_first_name='معصومه', co1_last_name='عباسی', co1_father_name='حسین', co1_national_id=national_id(987654321),
                            co1_role='spouse', co1_national_card=[upload('c1.png'), upload('c2.png')])
        second = permit.people.get(order=1)
        self.assertEqual((second.role, second.first_name), ('spouse', 'معصومه'))
        self.assertEqual(second.documents.filter(kind='national_card').count(), 2)
        self.assertEqual(permit.documents.filter(person__isnull=True).count(), 2)       # deed + shamim: the property's, no one's

    def test_mistakes_are_shown_and_nothing_is_saved(self):
        cases = {
            'national_id': dict(national_id='1234567890'),
            'phone': dict(phone='123'),
            'area': dict(area='abc'),
            'land_use': dict(land_use='castle'),
            'address': dict(address=''),
            'birth_date': dict(birth_date='1376/13/45'),
            'confirm': dict(confirm=None),
            'ownership_type': dict(ownership_type='none'),
            'national_card': dict(national_card=None),
            'birth_cert': dict(birth_cert=None),
            'shamim': dict(shamim=None),
            'deed': dict(deed=None),
            'renewal_code': dict(renewal_code='12'),
        }
        for field, change in cases.items():
            response = self.file(**change)
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.context['errors'], field)
        self.assertFalse(PermitFile.objects.exists())
        self.assertFalse(ServiceRequest.objects.filter(request_type='building_permit').exists())

    def test_the_paper_must_match_the_chosen_ownership(self):
        response = self.file(ownership='bonyad', bonyad_contract=None, deed=upload('d.pdf', PDF))
        self.assertIn('bonyad_contract', response.context['errors'])

    def test_wrong_file_types_are_refused(self):
        for name, content in (('x.exe', b'MZ' + b'\x00' * 20), ('fake.png', b'not a picture')):       # the site-wide upload guard
            response = self.file(national_card=[upload(name, content)])
            self.assertEqual(response.status_code, 400, name)
        response = self.file(shamim=upload('plot.pdf', PDF))                                           # allowed site-wide, not for a shamim
        self.assertIn('shamim', response.context['errors'])
        self.assertFalse(PermitFile.objects.exists())

    def test_a_zip_shamim_is_accepted(self):
        permit = self.filed(shamim=upload('plot.zip', b'PK\x03\x04' + b'\x00' * 30))
        self.assertTrue(permit.documents.filter(kind='shamim', original_name='plot.zip').exists())

    def test_a_locked_plot_cannot_be_applied_for(self):
        village_map = VillageMap.objects.get(slug='dastgerd')
        parcel = MapParcel.objects.filter(village_map=village_map).exclude(renewal_code='').first()
        ParcelLock.objects.create(parcel=parcel, reason='debt')
        response = self.file(renewal_code=parcel.renewal_code)
        self.assertEqual(response.status_code, 400)
        self.assertIn('قفل', response.context['errors']['renewal_code'])
        self.assertFalse(PermitFile.objects.exists())

    def test_the_old_permit_address_leads_to_the_same_form(self):
        self.assertEqual(client_for(self.citizen).get(reverse('main:construction_permit_request')).status_code, 200)


class Visibility(Village):
    def setUp(self):
        super().setUp()
        self.permit = self.filed()

    def see(self, who, name='permit_file', *args):
        return client_for(who).get(reverse(f'main:{name}', args=args or [self.permit.pk]))

    def test_the_owner_and_the_villages_staff_open_it(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(self.see(who).status_code, 200, who.profile.role)

    def test_nobody_else_does(self):
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(self.see(who).status_code, 404, who.profile.role)
        self.assertEqual(self.client.get(reverse('main:permit_file', args=[self.permit.pk])).status_code, 302)

    def test_the_file_page_shows_the_people_the_papers_and_the_steps(self):
        page = self.see(self.clerk).content.decode()
        self.assertIn(national_id(123456789).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')), page)
        self.assertIn('تأیید مالکیت و مدارک مکان‌محور', page)
        self.assertIn('افتتاح پرونده و دادن کد نوسازی', page)           # the clerk's form
        self.assertNotIn('افتتاح پرونده و دادن کد نوسازی', self.see(self.citizen).content.decode())

    def test_papers_are_served_only_to_the_owner_and_the_villages_staff(self):
        doc = self.permit.documents.filter(kind='national_card').first()
        url = reverse('main:permit_document', args=[doc.pk])
        for who in (self.citizen, self.clerk, self.dehyari, self.engineer):
            response = client_for(who).get(url)
            self.assertEqual(response.status_code, 200, who.profile.role)
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertIn('inline', response['Content-Disposition'])
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(url).status_code, 404, who.profile.role)
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_the_shamim_file_is_a_download_never_shown_in_the_browser(self):
        doc = self.permit.documents.get(kind='shamim')
        response = client_for(self.clerk).get(reverse('main:permit_document', args=[doc.pk]))
        self.assertIn('attachment', response['Content-Disposition'])


class Opening(Village):
    CODE = '0-0-8-182-2'

    def setUp(self):
        super().setUp()
        self.map = VillageMap.objects.get(slug='dastgerd')
        self.parcel = MapParcel.objects.filter(village_map=self.map, renewal_code=self.CODE).first()
        self.assertIsNotNone(self.parcel)
        self.permit = self.filed(lot_number='233')

    def open(self, who=None, code=None, **extra):
        return client_for(who or self.clerk).post(reverse('main:permit_open', args=[self.permit.pk]),
                                                  {'renewal_code': self.CODE if code is None else code, 'notes': 'مدارک کامل بود', **extra}, follow=True)

    def reload(self):
        self.permit.refresh_from_db()
        self.permit.request.refresh_from_db()
        return self.permit

    def test_the_clerk_opens_the_file_and_it_moves_to_step_two(self):
        self.open()
        permit = self.reload()
        self.assertEqual((permit.state, permit.stage_no, permit.renewal_code, permit.parcel_id, permit.opened_by),
                         ('done', 2, self.CODE, self.parcel.pk, self.clerk))
        sr = permit.request
        self.assertEqual((sr.status, sr.parcel_number), ('in_review', self.CODE))
        self.assertTrue(any('افتتاح' in h['action'] for h in sr.workflow_history))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title__contains='افتتاح شد').exists())

    def test_the_engineer_and_the_dehyari_may_open_it_too(self):
        for who in (self.engineer, self.dehyari):
            permit = self.filed()
            self.permit = permit
            self.open(who)
            self.assertEqual(self.reload().state, 'done', who.profile.role)

    def test_the_plot_on_the_map_gets_the_owner_and_the_permit(self):
        self.open()
        archive = ParcelArchive.objects.get(parcel=self.parcel)
        self.assertEqual((archive.building_owner_name, archive.building_owner_national_id), ('علی رضایی', national_id(123456789)))
        self.assertEqual(archive.owner_name, 'علی رضایی')                  # a deed: the applicant owns the land too
        self.assertIn(f'پرونده پروانه {self.permit.pk}', archive.permit_notes)

    def test_for_a_bonyad_contract_the_land_belongs_to_the_bonyad(self):
        self.permit = self.filed(ownership='bonyad')
        self.open()
        archive = ParcelArchive.objects.get(parcel=self.parcel)
        self.assertEqual(archive.owner_name, 'بنیاد مسکن انقلاب اسلامی')
        self.assertEqual(archive.building_owner_name, 'علی رضایی')

    def test_what_the_staff_already_wrote_on_the_plot_is_not_overwritten(self):
        ParcelArchive.objects.create(parcel=self.parcel, owner_name='مالک قبلی', permit_number='1403/5')
        self.open()
        archive = ParcelArchive.objects.get(parcel=self.parcel)
        self.assertEqual((archive.owner_name, archive.permit_number), ('مالک قبلی', '1403/5'))
        self.assertEqual(archive.building_owner_name, 'علی رضایی')

    def test_the_plots_lot_number_is_filled_in_when_it_was_blank(self):
        MapParcel.objects.filter(pk=self.parcel.pk).update(lot_no='')
        self.open()
        self.parcel.refresh_from_db()
        self.assertEqual(self.parcel.lot_no, '233')

    def test_the_code_is_checked(self):
        for bad in ('', '12', 'abc', '1-2-3'):
            self.open(code=bad)
            self.assertEqual(self.reload().state, 'submitted', bad)

    def test_persian_digits_and_other_separators_are_understood(self):
        self.open(code='۰ / ۰ / ۸ / ۱۸۲ / ۲')
        self.assertEqual(self.reload().renewal_code, self.CODE)

    def test_a_code_the_map_does_not_have_is_kept_without_a_plot(self):
        self.open(code='0-0-9999-999-9')
        permit = self.reload()
        self.assertEqual((permit.state, permit.renewal_code, permit.parcel), ('done', '0-0-9999-999-9', None))

    def test_two_plots_with_one_code_need_the_clerks_choice(self):
        twins = list(MapParcel.objects.filter(village_map=self.map).exclude(renewal_code='').values_list('renewal_code', flat=True))
        code = next(c for c in set(twins) if twins.count(c) > 1)
        first, second = MapParcel.objects.filter(renewal_code=code)[:2]
        self.open(code=code)
        self.assertEqual(self.reload().state, 'submitted')
        self.open(code=code, parcel_id=second.pk)
        self.assertEqual(self.reload().parcel_id, second.pk)

    def test_a_locked_plot_cannot_get_a_file_opened(self):
        ParcelLock.objects.create(parcel=self.parcel, reason='neighbor_complaint')
        self.open()
        self.assertEqual(self.reload().state, 'submitted')

    def test_only_the_staff_of_this_village_open_files(self):
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.open(who)
            self.assertEqual(self.reload().state, 'submitted', who.profile.role)

    def test_opening_twice_changes_nothing_the_second_time(self):
        self.open()
        self.open(code='0-0-9999-999-9')
        self.assertEqual(self.reload().renewal_code, self.CODE)

    def test_get_is_not_allowed(self):
        self.assertEqual(client_for(self.clerk).get(reverse('main:permit_open', args=[self.permit.pk])).status_code, 405)

    def test_send_back_asks_for_papers_and_the_citizen_answers(self):
        client = client_for(self.clerk)
        client.post(reverse('main:permit_send_back', args=[self.permit.pk]), {'notes': ' '})
        self.assertEqual(self.reload().state, 'submitted')                     # the note is required
        client.post(reverse('main:permit_send_back', args=[self.permit.pk]), {'notes': 'پشت کارت ملی خوانا نیست'})
        permit = self.reload()
        self.assertEqual((permit.state, permit.request.status), ('needs_docs', 'requires_documents'))
        mine = client_for(self.citizen)
        for kind in ('national_card',):
            mine.post(reverse('main:permit_supplement', args=[permit.pk]), {'kind': kind, 'document': [upload('again.png')]})
        permit = self.reload()
        self.assertEqual((permit.state, permit.request.status), ('submitted', 'pending'))
        self.assertTrue(permit.documents.filter(original_name='again.png').exists())

    def test_only_the_owner_adds_papers_and_only_when_asked(self):
        client_for(self.citizen).post(reverse('main:permit_supplement', args=[self.permit.pk]), {'kind': 'other', 'document': [upload('x.png')]})
        self.assertFalse(self.permit.documents.filter(original_name='x.png').exists())      # nothing was asked for
        self.client_clerk = client_for(self.clerk)
        self.client_clerk.post(reverse('main:permit_send_back', args=[self.permit.pk]), {'notes': 'ناقص'})
        client_for(self.neighbour).post(reverse('main:permit_supplement', args=[self.permit.pk]), {'kind': 'other', 'document': [upload('y.png')]})
        self.assertFalse(self.permit.documents.filter(original_name='y.png').exists())

    def test_refusing_needs_a_reason_and_ends_the_file(self):
        client = client_for(self.engineer)
        client.post(reverse('main:permit_refuse', args=[self.permit.pk]), {'notes': ''})
        self.assertEqual(self.reload().state, 'submitted')
        client.post(reverse('main:permit_refuse', args=[self.permit.pk]), {'notes': 'ملک در حریم است'})
        permit = self.reload()
        self.assertEqual((permit.state, permit.request.status), ('rejected', 'rejected'))


class InThePanels(Village):
    def setUp(self):
        super().setUp()
        self.permit = self.filed()

    def test_the_clerk_desk_lists_the_waiting_files_in_a_tab(self):
        response = client_for(self.clerk).get(reverse('main:clerk_dashboard'), {'tab': 'files'})
        self.assertContains(response, reverse('main:permit_file', args=[self.permit.pk]))
        self.assertContains(response, 'علی')
        self.assertEqual(client_for(self.clerk).get(reverse('main:clerk_dashboard')).context['stats']['permit_files'], 1)

    def test_the_expert_panel_has_the_list(self):
        page = client_for(self.engineer).get(reverse('main:dehyari_expert_dashboard')).content.decode()
        self.assertIn('id="permits-section"', page)
        self.assertIn(reverse('main:permit_file', args=[self.permit.pk]), page)

    def test_the_dehyari_panel_has_a_tab_for_them(self):
        response = client_for(self.dehyari).get(reverse('main:mayor_panel', args=['permits']))
        self.assertContains(response, reverse('main:permit_file', args=[self.permit.pk]))
        self.assertContains(client_for(self.dehyari).get(reverse('main:dehyari_dashboard')), 'data-page="permits"')

    def test_other_villages_staff_see_an_empty_list(self):
        response = client_for(self.stranger_clerk).get(reverse('main:clerk_dashboard'), {'tab': 'files'})
        self.assertNotContains(response, reverse('main:permit_file', args=[self.permit.pk]))

    def test_opened_files_show_on_the_plots_card_with_who_asked_for_what(self):
        parcel = MapParcel.objects.get(village_map__slug='dastgerd', renewal_code='0-0-8-182-2')
        client_for(self.clerk).post(reverse('main:permit_open', args=[self.permit.pk]), {'renewal_code': parcel.renewal_code})
        ServiceRequest.objects.create(user=self.neighbour, request_type='other', title='شکایت از اشغال معبر', description='d',
                                      parcel_number=parcel.renewal_code)
        admin = make_user('admin')
        data = client_for(admin).get(reverse('main:gis_parcel', args=['dastgerd', parcel.pk])).json()['parcel']
        kinds = {r['kind']: r for r in data['requests']}
        self.assertEqual(set(kinds), {'permit', 'request'})
        self.assertEqual(kinds['permit']['who'], 'علی رضایی')
        self.assertEqual(kinds['permit']['url'], reverse('main:permit_file', args=[self.permit.pk]))
        self.assertEqual(data['archive']['building_owner_name'], 'علی رضایی')

    def test_the_map_card_of_a_plot_nobody_asked_about_has_no_requests(self):
        parcel = MapParcel.objects.filter(village_map__slug='dastgerd').exclude(renewal_code='').first()
        data = client_for(make_user('admin')).get(reverse('main:gis_parcel', args=['dastgerd', parcel.pk])).json()['parcel']
        self.assertEqual(data['requests'], [])
