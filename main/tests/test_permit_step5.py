"""Building permit, steps 5 and 6: the fee rows, the owner's answer, the payments and the Social Security letter."""
from django.contrib.auth.models import User
from django.urls import reverse

from main.models import Notification
from main.office import permit_step5, permits
from main.tests.helpers import client_for, make_user
from main.tests.test_permit_files import PDF, upload
from main.tests.test_permit_step4 import AtStepFour


class AtStepFive(AtStepFour):
    """The plans are signed: the financial officer has the fees to define."""

    def setUp(self):
        super().setUp()
        self.officer = User.objects.get(pk=make_user('accountant', city_village=self.village).pk)
        self.foreign_officer = User.objects.get(pk=make_user('accountant', city_village='روستای دیگر').pk)
        self.ready()
        self.submit()
        self.review()
        self.sign()
        self.reload()
        self.assertEqual(self.permit.stage_no, 5)

    def fees(self, who=None, name='fees_save', **data):
        base = {'r2_on': 'on', 'r2_amount': '85,800,000', 'r2_built': '120', 'r2_b': '۱/۳', 'r2_value': '220000', 'r2_coef': '5', 'r2_height': '0.5',
                'r29_on': 'on', 'r29_amount': '1100000', 'x1_title': 'عوارض تفکیک عرصه', 'x1_amount': '3300000'}
        base.update(data)
        return client_for(who or self.officer).post(self.url(name), {k: v for k, v in base.items() if v is not None})

    def offer(self, who=None, **data):
        return self.fees(who, 'fees_offer', **data)

    def approve(self, who=None):
        return client_for(who or self.citizen).post(self.url('fees_approve'))

    def at_step_six(self):
        self.offer()
        self.approve()
        self.reload()
        self.assertEqual(self.permit.stage_no, 6)

    def pay(self, who=None, **data):
        base = {'slip_no': '005952', 'date': '1405/07/26', 'amount': '90200000'}
        base.update(data)
        return client_for(who or self.citizen).post(self.url('pay_add'), {k: v for k, v in base.items() if v is not None})

    def letter(self, who=None, **data):
        base = {'number': '18/2117', 'date': '1405/08/10', 'branch': 'بیرجند', 'base': '85800000', 'area': '120', 'street': '12', 'no_formula': 'on'}
        base.update(data)
        return client_for(who or self.clerk).post(self.url('letter_issue'), {k: v for k, v in base.items() if v is not None})


class Catalogue(AtStepFive):
    def test_the_form_has_31_numbered_rows(self):
        self.assertEqual([r['no'] for r in permit_step5.ROWS], list(range(1, 32)))
        self.assertEqual(permit_step5.ROWS[1]['title'], 'عوارض احداث بنا طبقه همکف')
        self.assertEqual(permit_step5.ROWS[5]['title'], 'بهای خدمات مدیریت پسماند مسکونی')
        self.assertEqual(permit_step5.ROWS[27]['title'], 'بهای کارشناسی')


class DefiningTheFees(AtStepFive):
    def test_the_officer_is_told_when_the_plans_are_signed(self):
        self.assertTrue(Notification.objects.filter(user=self.officer, title='عوارض پرونده‌ی پروانه').exists())
        self.assertFalse(Notification.objects.filter(user=self.foreign_officer, title='عوارض پرونده‌ی پروانه').exists())
        self.assertEqual(self.permit.status_text, 'منتظر تعیین عوارض (مسئول مالی)')

    def test_saving_keeps_the_rows_and_the_total_and_tells_nobody(self):
        self.fees()
        permit = self.reload()
        self.assertEqual(permit.fees['total'], 90200000)
        self.assertEqual(permit.fees['rows']['2']['amount'], 85800000)
        self.assertEqual(permit.fees['rows']['2']['f'], {'built': '120', 'b': '1.3', 'value': '220000', 'coef': '5', 'height': '0.5'})
        self.assertEqual(permit.fees['extra'], [{'title': 'عوارض تفکیک عرصه', 'amount': 3300000}])
        self.assertEqual(permit.fees_state, '')
        self.assertFalse(Notification.objects.filter(user=self.citizen, title__contains='عوارض').exists())
        self.assertEqual(permit_step5.building_fees(permit.fees), 85800000)

    def test_offering_sends_it_to_the_owner(self):
        self.offer()
        permit = self.reload()
        self.assertEqual((permit.fees_state, permit.fees_by), ('offered', self.officer))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='عوارض پرونده‌ی شما تعیین شد').exists())
        self.assertEqual(permit.status_text, 'عوارض منتظر تایید متقاضی')

    def test_mistakes_save_nothing(self):
        cases = [dict(r2_amount=''), dict(r2_amount='abc'), dict(r2_amount='-5'), dict(x1_amount=''), dict(x1_title='')]
        for change in cases:
            self.offer(**change)
            self.assertEqual(self.reload().fees_state, '', change)
            self.assertFalse(self.permit.fees, change)
        self.offer(r2_on=None, r29_on=None, x1_title=None, x1_amount=None)
        self.assertEqual(self.reload().fees_state, '')

    def test_only_the_village_officer_or_dehyari_defines_the_fees(self):
        for who in (self.citizen, self.clerk, self.expert, self.foreign_officer, self.stranger):
            self.fees(who)
        self.assertFalse(self.reload().fees)
        self.fees(self.dehyari)
        self.assertEqual(self.reload().fees['total'], 90200000)

    def test_nothing_changes_once_offered(self):
        self.offer()
        self.fees(r2_amount='1')
        self.assertEqual(self.reload().fees['total'], 90200000)

    def test_not_before_the_plans_are_signed(self):
        self.permit.stage_no = 4
        self.permit.save()
        self.fees()
        self.assertFalse(self.reload().fees)


class TheOwnersAnswer(AtStepFive):
    def test_the_owner_approves_and_the_file_moves_to_step_six(self):
        self.offer()
        self.approve()
        permit = self.reload()
        self.assertEqual((permit.stage_no, permit.fees_state), (6, 'approved'))
        self.assertEqual(permit.status_text, 'منتظر پرداخت عوارض')
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='عوارض تایید شد').exists())

    def test_only_the_owner_answers_and_only_an_offered_list(self):
        self.approve()
        self.assertEqual(self.reload().stage_no, 5)
        self.offer()
        for who in (self.clerk, self.officer, self.neighbour, self.stranger):
            self.approve(who)
        self.assertEqual(self.reload().stage_no, 5)

    def test_an_objection_goes_back_to_the_officer_who_revises(self):
        self.offer()
        client_for(self.neighbour).post(self.url('fees_object'), {'notes': 'x'})
        client_for(self.citizen).post(self.url('fees_object'), {'notes': ''})
        self.assertEqual(self.reload().fees_state, 'offered')
        client_for(self.citizen).post(self.url('fees_object'), {'notes': 'ردیف ۲ زیاد است'})
        permit = self.reload()
        self.assertEqual((permit.fees_state, permit.fees['objection']), ('objected', 'ردیف ۲ زیاد است'))
        self.assertTrue(Notification.objects.filter(user=self.officer, title='اعتراض به عوارض').exists())
        self.assertTrue(permit.needs_accountant)
        self.offer(r2_amount='80000000')
        permit = self.reload()
        self.assertEqual((permit.fees_state, permit.fees['total']), ('offered', 84400000))


class Payments(AtStepFive):
    def setUp(self):
        super().setUp()
        self.at_step_six()

    def test_a_slip_the_owner_types_waits_for_the_staff(self):
        self.pay(slip_no='۰۰۵۹۵۲')
        permit = self.reload()
        pay = permit.insurance['payments'][0]
        self.assertEqual((pay['slip_no'], pay['date'], pay['amount'], pay['ok']), ('005952', '1405/07/26', 90200000, False))
        self.assertFalse(permit.paid_up)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='فیش پرداخت عوارض').exists())
        self.assertTrue(permit.needs_staff)
        client_for(self.clerk).post(self.url('pay_confirm', pay['id']))
        permit = self.reload()
        self.assertTrue(permit.paid_up)
        self.assertEqual(permit.status_text, 'منتظر صدور معرفی‌نامه‌ی تامین اجتماعی')

    def test_the_officer_may_confirm_too_but_the_owner_may_not(self):
        self.pay()
        pid = self.reload().insurance['payments'][0]['id']
        client_for(self.citizen).post(self.url('pay_confirm', pid))
        client_for(self.foreign_officer).post(self.url('pay_confirm', pid))
        self.assertFalse(self.reload().paid_up)
        client_for(self.officer).post(self.url('pay_confirm', pid))
        self.assertTrue(self.reload().paid_up)

    def test_a_payment_the_staff_record_counts_at_once(self):
        self.pay(self.clerk)
        self.assertTrue(self.reload().paid_up)

    def test_partial_payments_add_up(self):
        self.pay(self.clerk, amount='50000000', slip_no='1')
        self.assertFalse(self.reload().paid_up)
        self.pay(self.clerk, amount='40200000', slip_no='2')
        self.assertTrue(self.reload().paid_up)

    def test_mistakes_and_repeats_are_refused(self):
        for change in (dict(amount=''), dict(amount='x'), dict(slip_no=''), dict(date='1405/13/40'), dict(date='')):
            self.pay(**change)
        self.assertFalse(self.reload().insurance.get('payments'))
        self.pay()
        self.pay()
        self.assertEqual(len(self.reload().insurance['payments']), 1)

    def test_the_slip_scan_is_kept_privately_and_staff_and_officer_may_open_it(self):
        client_for(self.citizen).post(self.url('pay_add'), {'slip_no': '9', 'date': '1405/07/26', 'amount': '1000', 'slip': upload('slip.pdf', PDF)})
        doc = self.reload().documents.get(kind='fee_receipt')
        link = reverse('main:permit_document', args=[doc.pk])
        for who, code in ((self.citizen, 200), (self.clerk, 200), (self.officer, 200), (self.neighbour, 404), (self.foreign_officer, 404), (self.stranger, 404)):
            self.assertEqual(client_for(who).get(link).status_code, code, who)

    def test_removing_a_payment(self):
        self.pay()
        pid = self.reload().insurance['payments'][0]['id']
        client_for(self.neighbour).post(self.url('pay_remove', pid))
        self.assertEqual(len(self.reload().insurance['payments']), 1)
        client_for(self.citizen).post(self.url('pay_remove', pid))
        self.assertFalse(self.reload().insurance['payments'])
        self.pay(self.clerk)
        pid = self.reload().insurance['payments'][0]['id']
        client_for(self.citizen).post(self.url('pay_remove', pid))     # a confirmed one: the owner may not
        self.assertEqual(len(self.reload().insurance['payments']), 1)


class TheLetter(AtStepFive):
    def setUp(self):
        super().setUp()
        self.at_step_six()

    def test_not_before_the_fees_are_paid(self):
        self.letter()
        self.assertEqual(self.reload().insurance_state, '')
        self.pay(self.clerk, amount='1000')
        self.letter()
        self.assertEqual(self.reload().insurance_state, '')

    def test_the_staff_issue_it_once_paid(self):
        self.pay(self.clerk)
        for who in (self.citizen, self.officer, self.neighbour, self.stranger):
            self.letter(who)
        self.assertEqual(self.reload().insurance_state, '')
        self.letter()
        permit = self.reload()
        self.assertEqual(permit.insurance_state, 'introduced')
        self.assertEqual((permit.insurance['letter']['branch'], permit.insurance['letter']['base']), ('بیرجند', 85800000))
        self.assertEqual(permit.status_text, 'معرفی‌نامه‌ی تامین اجتماعی صادر شد')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='معرفی‌نامه‌ی تامین اجتماعی آماده است').exists())
        self.letter(branch='دیگر')
        self.assertEqual(self.reload().insurance['letter']['branch'], 'بیرجند')

    def test_mistakes_issue_nothing(self):
        self.pay(self.clerk)
        for change in (dict(branch=''), dict(base=''), dict(base='x'), dict(number=''), dict(date='bad')):
            self.letter(**change)
            self.assertEqual(self.reload().insurance_state, '', change)

    def test_the_letter_defaults_come_from_the_file(self):
        self.pay(self.clerk)
        data = permit_step5.letter_defaults(self.reload())
        self.assertEqual((data['owner'], data['base'], data['street']), ('علی رضایی', 85800000, 12))
        self.assertEqual(data['total'], 90200000)
        self.assertEqual(data['area'], 135.0)               # the allowed building area of the Bonyad's answer

    def test_payments_are_frozen_after_the_letter(self):
        self.pay(self.clerk)
        self.letter()
        self.pay(self.clerk, slip_no='77')
        self.assertEqual(len(self.reload().insurance['payments']), 1)


class Pages(AtStepFive):
    def test_everyone_sees_what_belongs_to_them(self):
        page = client_for(self.officer).get(self.url('fees'))
        self.assertContains(page, 'ردیف‌های عوارض و بهای خدمات')
        self.assertContains(page, 'name="r31_amount"')
        for who, code in ((self.citizen, 200), (self.clerk, 200), (self.dehyari, 200), (self.neighbour, 404), (self.foreign_officer, 404), (self.stranger, 404)):
            self.assertEqual(client_for(who).get(self.url('fees')).status_code, code, who)
        owner_page = client_for(self.citizen).get(self.url('fees')).content.decode()
        self.assertNotIn('name="r31_amount"', owner_page)
        self.assertIn('امضا و تحویل دستی', owner_page)

    def test_the_owner_sees_the_offered_list_and_the_buttons(self):
        self.offer()
        page = client_for(self.citizen).get(self.url('fees')).content.decode()
        self.assertIn('۹۰٬۲۰۰٬۰۰۰', page)
        self.assertIn('تایید عوارض و رفتن به مرحله‌ی تامین اجتماعی', page)
        self.assertNotIn('تایید عوارض و رفتن', client_for(self.clerk).get(self.url('fees')).content.decode())

    def test_the_page_is_not_open_before_step_five(self):
        self.permit.stage_no = 4
        self.permit.save()
        self.assertEqual(client_for(self.citizen).get(self.url('fees')).status_code, 302)
        self.assertEqual(client_for(self.officer).get(self.url('fees')).status_code, 404)

    def test_the_letter_page_prefills_the_form(self):
        self.at_step_six()
        self.pay(self.clerk)
        page = client_for(self.clerk).get(self.url('fees')).content.decode()
        self.assertIn('name="branch"', page)
        self.assertIn('pfi-canvas', page)
        self.assertNotIn('pfi-canvas', client_for(self.citizen).get(self.url('fees')).content.decode())

    def test_the_officer_dashboard_lists_the_file(self):
        rows = permits.fee_rows_for(self.officer)
        self.assertEqual((len(rows['rows']), rows['waiting']), (1, 1))
        self.assertEqual(permits.fee_rows_for(self.foreign_officer)['rows'], [])
        page = client_for(self.officer).get(reverse('main:accountant_dashboard')).content.decode()
        self.assertIn('تعیین عوارض', page)

    def test_the_staff_panels_count_the_waiting_step_six_files(self):
        self.at_step_six()
        self.pay()
        self.assertEqual(permits.panel_rows(self.clerk)['waiting'], 1)
        self.assertTrue(self.reload().needs_staff)

    def test_the_paper_notice_shows_at_every_step(self):
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn('امضا و تحویل دستی', page)
        self.assertIn('فرم محاسبه‌ی عوارض', page)
