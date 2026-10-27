"""Building permit supervision: forms 8-13, the technical supervisor of the file, the Article 99 commission, messages, amendments."""
from django.contrib.auth.models import User
from django.urls import reverse

from main.models import Notification
from main.office import permit_step4, permit_step7, permit_supervision
from main.tests.helpers import client_for, make_user
from main.tests.test_permit_extension import Issued
from main.tests.test_permit_files import upload


class Supervised(Issued):
    def setUp(self):
        super().setUp()
        self.inspector = User.objects.get(pk=make_user('inspector', city_village=self.village).pk)
        self.other_inspector = User.objects.get(pk=make_user('inspector', city_village=self.village).pk)
        self.foreign_inspector = User.objects.get(pk=make_user('inspector', city_village='روستای دیگر').pk)

    def act(self, name, n=None, who=None, data=None, **files):
        args = (n,) if n is not None else ()
        return client_for(who or self.clerk).post(self.url(f'sup_{name}', *args), data or {}, **files)

    def link_inspector(self, who=None):
        return client_for(who or self.clerk).post(self.url('sup_assign'), {'supervisor': self.inspector.pk})

    def inspect_form(self, n, who=None, result='ok', **change):
        count = len(permit_supervision.ITEMS[n])
        data = {f'c_{i}': 'a' for i in range(1, count + 1)}
        data.update({'result': result, 'notes': 'ok' if result == 'ok' else 'ستون‌ها جابه‌جاست', **change})
        data = {k: v for k, v in data.items() if v is not None}
        return self.act('fill', n, who or self.inspector, data)

    def sign_up(self, n, who=None):
        return client_for(who or self.citizen).post(self.url('sup_upload', n), {'signed': [upload('s1.png'), upload('s2.png')]})

    def form_state(self, n):
        self.reload()
        return permit_supervision.forms(self.permit)[n]['state']

    def run_form(self, n):
        if n in permit_supervision.ITEMS:
            self.link_inspector()
            self.inspect_form(n)
        self.sign_up(n)
        self.act('approve', n)


class TheInspectorOfTheFile(Supervised):
    def test_the_staff_link_one_of_the_villages_inspectors(self):
        self.link_inspector()
        self.assertEqual(self.reload().supervisor, self.inspector)
        self.assertTrue(Notification.objects.filter(user=self.inspector, title='پرونده‌ی ساخت به شما سپرده شد').exists())
        client_for(self.clerk).post(self.url('sup_assign'), {'supervisor': self.foreign_inspector.pk})
        self.assertEqual(self.reload().supervisor, self.inspector)
        client_for(self.clerk).post(self.url('sup_assign'), {'supervisor': ''})
        self.assertIsNone(self.reload().supervisor)

    def test_only_staff_link_him(self):
        for who in (self.citizen, self.inspector, self.neighbour, self.officer):
            self.link_inspector(who)
        self.assertIsNone(self.reload().supervisor)

    def test_he_sees_only_his_own_files_and_not_the_identity_papers(self):
        self.link_inspector()
        mine = client_for(self.inspector).get(reverse('main:permit_file', args=[self.permit.pk]))
        self.assertEqual(mine.status_code, 200)
        self.assertNotIn('مدرک هویتی بارگذاری نشده', mine.content.decode())
        for who in (self.other_inspector, self.foreign_inspector):
            self.assertEqual(client_for(who).get(reverse('main:permit_file', args=[self.permit.pk])).status_code, 404)
        self.assertEqual(client_for(self.other_inspector).get(self.url('supervision')).status_code, 404)

    def test_his_dashboard_lists_the_file(self):
        self.link_inspector()
        page = client_for(self.inspector).get(reverse('main:inspector_dashboard')).content.decode()
        self.assertIn('پرونده‌های ساخت تحت نظارت من', page)
        self.assertIn(self.url('supervision'), page)
        other = client_for(self.other_inspector).get(reverse('main:inspector_dashboard')).content.decode()
        self.assertNotIn(self.url('supervision'), other)


class TheForms(Supervised):
    def test_form_eight_is_first_and_filled_from_the_file(self):
        self.assertEqual(permit_supervision.current(self.reload()), 8)
        data = permit_supervision.payload(self.permit)[8]['f']
        self.assertEqual((data['owner'], data['permit_no'], data['sup_name']), ('علی رضایی', '18/1286', 'سعید احمدی'))
        self.assertEqual(data['pledge_no'], permit_step4.payload(self.permit)['forms']['f07']['number'])

    def test_the_owner_uploads_and_one_of_the_staff_confirms(self):
        self.sign_up(8)
        self.assertEqual(self.form_state(8), 'uploaded')
        self.assertEqual(self.permit.documents.filter(kind='supervision_form').count(), 2)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='فرم نظارت رسید').exists())
        for who in (self.citizen, self.neighbour, self.inspector, self.stranger):
            self.act('approve', 8, who)
        self.assertEqual(self.form_state(8), 'uploaded')
        self.act('approve', 8, self.expert)
        self.assertEqual((self.form_state(8), permit_supervision.current(self.permit)), ('approved', 9))

    def test_a_form_waits_for_its_turn(self):
        self.sign_up(9)
        self.act('fill', 9, self.clerk, {'result': 'ok'})
        self.assertEqual(self.form_state(9), 'open')
        self.assertFalse(permit_supervision.forms(self.permit)[9]['docs'])

    def test_forms_nine_to_twelve_need_the_inspection_before_the_upload(self):
        self.run_form(8)
        self.sign_up(9)
        self.assertEqual(self.form_state(9), 'open')
        self.link_inspector()
        self.inspect_form(9, result='ok', c_3=None)
        self.assertEqual(permit_supervision.forms(self.permit)[9]['result'], '')
        self.inspect_form(9)
        self.assertEqual(permit_supervision.forms(self.reload())[9]['result'], 'ok')
        self.sign_up(9)
        self.assertEqual(self.form_state(9), 'uploaded')

    def test_the_owner_cannot_fill_the_inspection(self):
        self.run_form(8)
        self.inspect_form(9, who=self.citizen)
        self.inspect_form(9, who=self.other_inspector)
        self.assertEqual(permit_supervision.forms(self.reload())[9]['result'], '')

    def test_returning_a_form_lets_the_owner_send_it_again(self):
        self.sign_up(8)
        self.act('return', 8, data={'notes': ''})
        self.assertEqual(self.form_state(8), 'uploaded')
        self.act('return', 8, data={'notes': 'امضا ناخوانا'})
        self.assertEqual(self.form_state(8), 'returned')
        self.sign_up(8)
        self.assertEqual(self.form_state(8), 'uploaded')
        self.assertEqual(self.permit.documents.filter(kind='supervision_form').count(), 2)

    def test_the_six_forms_in_turn_end_the_supervision(self):
        for n in permit_supervision.NUMBERS:
            self.run_form(n)
        permit = self.reload()
        self.assertEqual(permit.stage_no, 9)
        self.assertIsNone(permit_supervision.current(permit))
        self.assertEqual(permit.status_text, 'نظارت کامل شد؛ درخواست گواهی پایان کار از متقاضی')
        data = permit_supervision.payload(permit)[13]['f']
        self.assertEqual((data['s1_no'], data['s4_no']), (permit_supervision.forms(permit)[9]['f']['number'], permit_supervision.forms(permit)[12]['f']['number']))

    def test_the_status_line_follows_the_current_form(self):
        self.sign_up(8)
        self.assertEqual(self.reload().status_text, 'نظارت، فرم 8: منتظر تایید دهیاری')


class Violations(Supervised):
    def setUp(self):
        super().setUp()
        self.run_form(8)
        self.link_inspector()

    def test_a_violation_needs_notes_and_stops_the_form(self):
        self.inspect_form(9, result='violation', notes='')
        self.assertEqual(self.form_state(9), 'open')
        self.inspect_form(9, result='violation')
        self.assertEqual(self.form_state(9), 'violation')
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='گزارش تخلف در ساخت').exists())
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='گزارش تخلف در ساخت').exists())
        self.assertTrue(self.permit.needs_staff)
        self.sign_up(9)
        self.assertEqual(self.form_state(9), 'violation')

    def test_the_dehyari_refers_it_to_the_commission_and_records_the_decision(self):
        self.inspect_form(9, result='violation')
        self.act('refer', 9, self.citizen)
        self.assertEqual(self.form_state(9), 'violation')
        self.act('refer', 9, data={'case_ref': '55', 'case_date': '1405/08/20'})
        self.assertEqual(self.form_state(9), 'commission')
        self.act('decide', 9, data={'vote_no': '', 'decision': 'جریمه'})
        self.assertEqual(self.form_state(9), 'commission')
        self.act('decide', 9, data={'vote_no': '99/12', 'vote_date': '1405/09/01', 'decision': 'رفع تخلف و بازدید دوباره'})
        permit = self.reload()
        self.assertEqual(self.form_state(9), 'open')
        self.assertEqual(permit_supervision.forms(permit)[9]['result'], '')
        self.assertEqual(permit.supervision['commission'][0]['vote_no'], '99/12')
        self.inspect_form(9)
        self.sign_up(9)
        self.act('approve', 9)
        self.assertEqual(permit_supervision.current(self.reload()), 10)

    def test_the_vote_number_reaches_form_thirteen(self):
        self.inspect_form(9, result='violation')
        self.act('refer', 9)
        self.act('decide', 9, data={'vote_no': '99/12', 'decision': 'x'})
        self.assertEqual(permit_supervision.defaults(self.reload(), 13)['vote_no'], '99/12')


class Talking(Supervised):
    def test_the_owner_the_inspector_and_the_staff_exchange_messages(self):
        self.link_inspector()
        client_for(self.citizen).post(self.url('sup_message'), {'text': 'کی بازدید می‌کنید؟'})
        client_for(self.inspector).post(self.url('sup_message'), {'text': 'فردا صبح'})
        thread = permit_supervision.thread(self.reload())
        self.assertEqual([m['who'] for m in thread], ['متقاضی', 'ناظر فنی'])
        self.assertTrue(Notification.objects.filter(user=self.inspector, title='پیام تازه در پرونده').exists())
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='پیام تازه در پرونده').exists())
        page = client_for(self.citizen).get(self.url('supervision')).content.decode()
        self.assertIn('فردا صبح', page)

    def test_strangers_and_empty_messages_are_refused(self):
        self.link_inspector()
        for who in (self.neighbour, self.other_inspector, self.foreign_inspector):
            client_for(who).post(self.url('sup_message'), {'text': 'x'})
        client_for(self.citizen).post(self.url('sup_message'), {'text': '  '})
        self.assertFalse(permit_supervision.thread(self.reload()))


class TheAmendmentSheet(Supervised):
    def amend(self, who=None, **change):
        data = {f'f_{k}': v for k, v in permit_step7.am_payload(self.reload()).items()}
        data.update({f'f_{k}': v for k, v in change.items()})
        return client_for(who or self.clerk).post(self.url('licence_amend'), data)

    def test_it_starts_from_the_permit_and_the_staff_change_it(self):
        base = permit_step7.am_payload(self.reload())
        self.assertEqual((base['am_built'], base['am_fl_ground_area']), ('135', '135'))
        self.amend(am_fl_first_count='1', am_fl_first_area='60', am_notes='افزودن طبقه اول')
        saved = permit_step7.am_payload(self.reload())
        self.assertEqual((saved['am_fl_first_area'], saved['am_notes']), ('60', 'افزودن طبقه اول'))

    def test_only_the_staff_and_only_after_the_permit_is_issued(self):
        for who in (self.citizen, self.inspector, self.neighbour):
            self.amend(who, am_notes='x')
        self.assertNotIn('amend', self.reload().licence)
        page = client_for(self.clerk).get(self.url('licence')).content.decode()
        self.assertIn('اصلاحات و تغییرات پروانه', page)
        self.assertNotIn('اصلاحات و تغییرات پروانه', client_for(self.citizen).get(self.url('licence')).content.decode())
