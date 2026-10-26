"""Building permit, step 3: the owner brings the Bonyad's answer, the staff check it and the file moves on."""
from django.test import TestCase
from django.urls import reverse

from main.models import Notification, ParcelArchive, PermitFile
from main.office import geo, permit_step3, permits
from main.tests.helpers import client_for
from main.tests.test_permit_files import PDF, upload
from main.tests.test_permit_step2 import Village as FormsVillage


def answer(**override):
    data = {
        'answer': [upload('a1.png'), upload('a2.png')], 'letter_no': '14040046237394', 'tracking_code': '174944647338 3264',
        'letter_date': '۱۴۰۴/۰۳/۲۰', 'request_ref': '18/1835', 'verdict': 'allowed', 'valid_until': '1404/09/16',
        'total_area': '200', 'area_after': '200', 'usage': 'مسکونی', 'position': 'شمال', 'occupancy_pct': '60', 'occupancy_m2': '120',
        'floors': '1', 'density_pct': '60', 'floor_area': '135', 'height_total': '3.5', 'height_base': '3.5', 'permit_type': 'نوسازی',
    }
    data.update(override)
    return {k: v for k, v in data.items() if v is not None}


class AtStepThree(FormsVillage):
    """A file whose forms were handed over: it waits for the Bonyad's answer."""

    def setUp(self):
        super().setUp()
        self.open()
        self.form1(number='18/1835', request_no='18/1836')
        self.form2()
        client_for(self.clerk).post(reverse('main:permit_deliver', args=[self.permit.pk]))
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.stage_no, 3)

    def send(self, who=None, **override):
        return client_for(who or self.citizen).post(reverse('main:permit_answer', args=[self.permit.pk]), answer(**override))

    def decide(self, who=None, **override):
        data = {k: v for k, v in answer(**override).items() if k != 'answer'}
        data.setdefault('confirm', 'on')
        return client_for(who or self.clerk).post(reverse('main:permit_answer_verify', args=[self.permit.pk]), data)

    def reload(self):
        self.permit.refresh_from_db()
        self.permit.request.refresh_from_db()
        return self.permit


class SendingTheAnswer(AtStepThree):
    def test_the_owner_uploads_it_and_the_staff_are_told(self):
        self.send()
        permit = self.reload()
        self.assertEqual((permit.bonyad_state, permit.stage_no), ('uploaded', 3))
        self.assertEqual(permit.documents.filter(kind='bonyad_answer').count(), 2)
        self.assertEqual((permit.bonyad['tracking_code'], permit.bonyad['letter_date'], permit.bonyad['floors']), ('1749446473383264', '1404/03/20', 1))
        self.assertEqual(permit.bonyad['floor_area'], 135.0)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title__contains='پاسخ بنیاد').exists())
        self.assertEqual(permit.status_text, 'پاسخ بنیاد منتظر تایید صحت')

    def test_mistakes_save_nothing(self):
        cases = [dict(answer=None), dict(tracking_code=''), dict(tracking_code='12'), dict(letter_no=''), dict(letter_date='1404/13/40'),
                 dict(verdict=''), dict(verdict='maybe'), dict(floors='', verdict='allowed'), dict(floor_area=''), dict(occupancy_pct='150'),
                 dict(total_area='abc'), dict(floors='99'), dict(center_x='5')]
        for change in cases:
            self.send(**change)
            self.assertEqual(self.reload().bonyad_state, '', change)
        self.assertFalse(self.permit.documents.filter(kind='bonyad_answer').exists())

    def test_a_denial_needs_no_building_figures(self):
        self.send(verdict='denied', floors='', floor_area='', occupancy_pct='')
        self.assertEqual(self.reload().bonyad_state, 'uploaded')

    def test_only_the_owner_sends_it_and_only_once(self):
        for who in (self.clerk, self.neighbour, self.stranger):
            self.send(who)
        self.assertEqual(self.reload().bonyad_state, '')
        self.send()
        self.send(tracking_code='99999999999')
        self.assertEqual(self.reload().bonyad['tracking_code'], '1749446473383264')

    def test_not_before_step_three(self):
        PermitFile.objects.filter(pk=self.permit.pk).update(stage_no=2)
        self.send()
        self.assertEqual(self.reload().bonyad_state, '')

    def test_the_file_page_shows_each_side_its_own_part(self):
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(reverse('main:permit_answer', args=[self.permit.pk]), page)
        self.assertNotIn(reverse('main:permit_answer_verify', args=[self.permit.pk]), page)
        self.send()
        staff = client_for(self.clerk).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(reverse('main:permit_answer_verify', args=[self.permit.pk]), staff)
        mine = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertNotIn(reverse('main:permit_answer_verify', args=[self.permit.pk]), mine)
        self.assertNotIn(reverse('main:permit_answer', args=[self.permit.pk]), mine)

    def test_the_lists_count_it_as_waiting_for_the_staff(self):
        self.assertEqual(permits.panel_rows(self.clerk)['waiting'], 0)
        self.send()
        rows = permits.panel_rows(self.clerk)
        self.assertEqual(rows['waiting'], 1)
        self.assertTrue(rows['rows'][0].needs_staff)


class WhatTheSystemChecks(AtStepThree):
    def check(self, **override):
        self.send(**override)
        return {c['text']: c['status'] for c in permit_step3.checks(self.reload())}

    def states(self, **override):
        return sorted(set(self.check(**override).values()))

    def test_a_matching_answer_has_no_warnings(self):
        utm = dict(zip(('center_x', 'center_y'), (round(v) for v in self._centre_utm())))
        checks = self.check(total_area=str(self.permit.area_m2), area_after=None, letter_date='1405/08/05', valid_until='1499/01/01', **utm)
        self.assertNotIn('warn', checks.values(), checks)
        self.assertTrue(any('همان شماره‌ی ثبت فرم ۱' in text for text in checks))

    def _centre_utm(self):
        lat, lng = permit_step3._plot_centre(self.permit)         # pylint: disable=protected-access
        return geo.latlng_to_utm(lat, lng)

    def test_each_mismatch_is_pointed_out(self):
        checks = self.check(request_ref='18/1', total_area='350', letter_date='1400/01/01', valid_until='1400/02/02', center_x='700000', center_y='3600000')
        warns = [text for text, status in checks.items() if status == 'warn']
        self.assertGreaterEqual(len(warns), 5, checks)
        self.assertTrue(any('یکی نیست' in t for t in warns))
        self.assertTrue(any('اختلاف' in t for t in warns))
        self.assertTrue(any('پیش از تاریخ فرم ۱' in t for t in warns))
        self.assertTrue(any('گذشته' in t for t in warns))
        self.assertTrue(any('فاصله دارد' in t for t in warns))

    def test_a_tracking_code_used_in_another_file_is_flagged(self):
        self.send()
        other = PermitFile.objects.get(pk=self.permit.pk)
        copy = PermitFile.objects.create(request=self._another_request(), ownership_type='deed', bonyad={'tracking_code': '1749446473383264'})
        checks = {c['text']: c['status'] for c in permit_step3.checks(other)}
        self.assertEqual(checks['این کد رهگیری در پرونده‌ی دیگری هم استفاده شده است!'], 'warn')
        self.assertTrue(copy.pk)

    def _another_request(self):
        from main.tests.helpers import make_request
        return make_request(self.neighbour, request_type='building_permit')


class Confirming(AtStepThree):
    def setUp(self):
        super().setUp()
        self.send()

    def test_the_staff_confirm_and_the_file_moves_to_step_four(self):
        self.decide()
        permit = self.reload()
        self.assertEqual((permit.bonyad_state, permit.stage_no, permit.bonyad_checked_by), ('verified', 4, self.clerk))
        self.assertIsNotNone(permit.bonyad_checked_at)
        self.assertTrue(any('تایید صحت پاسخ بنیاد' in h['action'] for h in permit.request.workflow_history))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='پاسخ بنیاد مسکن تایید شد').exists())
        self.assertEqual(permit.status_text, 'پاسخ بنیاد تایید شد')

    def test_the_expert_and_the_dehyari_may_too(self):
        from main.tests.helpers import make_user
        expert = make_user('engineer', city_village=self.village)
        from django.contrib.auth.models import User
        expert = User.objects.get(pk=expert.pk)
        self.decide(expert)
        self.assertEqual(self.reload().stage_no, 4)

    def test_the_dehyari_confirms(self):
        self.decide(self.dehyari)
        self.assertEqual(self.reload().stage_no, 4)

    def test_the_tick_is_required(self):
        self.decide(confirm='')
        self.assertEqual(self.reload().bonyad_state, 'uploaded')

    def test_a_mistyped_figure_is_corrected_while_confirming(self):
        self.decide(floors='2', floor_area='270', tracking_code='1749446473383264')
        self.assertEqual((self.reload().bonyad['floors'], self.permit.bonyad['floor_area']), (2, 270.0))

    def test_nobody_else_confirms(self):
        for who in (self.citizen, self.neighbour, self.stranger):
            self.decide(who)
        self.assertEqual(self.reload().bonyad_state, 'uploaded')

    def test_confirming_twice_changes_nothing(self):
        self.decide()
        self.decide(floors='5', floor_area='999')
        self.assertEqual(self.reload().bonyad['floors'], 1)

    def test_the_plot_on_the_map_gets_the_answer(self):
        self.decide()
        note = ParcelArchive.objects.get(parcel=self.parcel).permit_notes
        self.assertIn(f'پاسخ بنیاد پرونده {self.permit.pk}:', note)
        self.assertIn('مجاز', note)
        self.assertIn('135', note)

    def test_a_denial_ends_the_file(self):
        self.decide(verdict='denied')
        permit = self.reload()
        self.assertEqual((permit.state, permit.request.status, permit.stage_no), ('rejected', 'rejected', 3))

    def test_sending_it_back_and_answering_again(self):
        client = client_for(self.clerk)
        url = reverse('main:permit_answer_return', args=[self.permit.pk])
        client.post(url, {'notes': ' '})
        self.assertEqual(self.reload().bonyad_state, 'uploaded')           # a reason is required
        client.post(url, {'notes': 'صفحه‌ی دوم ناخوانا است'})
        permit = self.reload()
        self.assertEqual((permit.bonyad_state, permit.request.status), ('rejected', 'requires_documents'))
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn('صفحه‌ی دوم ناخوانا است', page)
        self.send(tracking_code='5555555555555', answer=[upload('again.pdf', PDF)])
        permit = self.reload()
        self.assertEqual((permit.bonyad_state, permit.request.status, permit.bonyad['tracking_code']), ('uploaded', 'pending', '5555555555555'))
        self.assertEqual(permit.documents.filter(kind='bonyad_answer').count(), 3)

    def test_only_the_staff_send_it_back(self):
        for who in (self.citizen, self.neighbour, self.stranger):
            client_for(who).post(reverse('main:permit_answer_return', args=[self.permit.pk]), {'notes': 'x'})
        self.assertEqual(self.reload().bonyad_state, 'uploaded')

    def send(self, who=None, **override):
        return client_for(who or self.citizen).post(reverse('main:permit_answer', args=[self.permit.pk]), answer(**override))


class TheAnswerPapers(AtStepThree):
    def test_they_are_private_like_the_other_papers(self):
        self.send()
        doc = self.reload().documents.filter(kind='bonyad_answer').first()
        url = reverse('main:permit_document', args=[doc.pk])
        for who in (self.citizen, self.clerk, self.dehyari):
            self.assertEqual(client_for(who).get(url).status_code, 200)
        for who in (self.neighbour, self.stranger):
            self.assertEqual(client_for(who).get(url).status_code, 404)

    def test_wrong_types_are_refused(self):
        response = self.send(answer=[upload('x.exe', b'MZ' + b'\x00' * 20)])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.reload().bonyad_state, '')

    send = AtStepThree.send
