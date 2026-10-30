"""Construction without a permit, step 7: the fee sheet (the dehyari's workbooks), the payments, the instalment plan and its cheques."""
from django.test import SimpleTestCase
from django.urls import reverse

from main.models import Notification
from main.office import fee_tables, permit_dues
from main.tests.helpers import client_for
from main.tests.test_permit_files import PNG, upload
from main.tests.test_permit_notice import soon
from main.tests.test_permit_reply import Step6


class Calculator(SimpleTestCase):
    def test_the_dehyaris_sample_sheet_comes_to_the_printed_total(self):
        """A plot on an 8 m street: 72.28 m² ground floor, 64 m² first floor, 79.41 m² plot, 10.04 m of kerb: 851,874,240 rials."""
        inputs = fee_tables.defaults('8')
        inputs.update({'a_res_1': '72.28', 'a_res_2': '64', 'join': '79.41', 'curb_len': '10.04', 'annual': '79.41'})
        rows, total = fee_tables.compute(inputs)
        amounts = {r['no']: r['amount'] for r in rows}
        self.assertEqual((amounts[2], amounts[3], amounts[26]), (144_704_560, 157_696_000, 377_991_600))
        self.assertEqual((amounts[33], amounts[34], amounts[39]), (82_830_000, 66_264_000, 6_988_080))
        self.assertEqual(total, 851_874_240)

    def test_the_rates_follow_the_street_width(self):
        wide = fee_tables.defaults('30+')
        wide['a_res_1'] = '100'
        narrow = fee_tables.defaults('4-6')
        narrow['a_res_1'] = '100'
        self.assertEqual(fee_tables.compute(wide)[0][1]['amount'], round(6.5 * 220_000 * 2.8 * 100))
        self.assertEqual(fee_tables.compute(narrow)[0][1]['amount'], round(6.5 * 220_000 * 1.4 * 100))
        self.assertEqual(set(fee_tables.WIDTHS), {'4-6', '8', '10', '12', '14', '16', '18', '20', '25', '30', '30+'})

    def test_balcony_rows_and_the_fence_and_the_other_groups(self):
        inputs = fee_tables.defaults('10')
        inputs.update({'a_res_4': '10', 'a_com_1': '20', 'fence': '30'})
        amounts = {r['no']: r['amount'] for r in fee_tables.compute(inputs)[0]}
        self.assertEqual(amounts[5], round(80 * 220_000 * 1.7 * 10))
        self.assertEqual(amounts[8], round(10 * 440_000 * 1.7 * 20))
        self.assertEqual(amounts[25], 350_000 * 30)


class Step7(Step6):
    def setUp(self):
        super().setUp()
        self.reload()
        self.permit.reply_state = 'verified'
        self.permit.save()
        self.act(self.dehyari, 'permit_step6_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 7)

    def sheet_post(self, **over):
        post = fee_tables.defaults('8')
        post.update({'a_res_1': '72.28', 'a_res_2': '64', 'curb_len': '10.04', 'annual': '79.41'})
        post.update(over)
        return post

    def issue(self, who=None, **over):
        return client_for(who or self.accountant).post(self.url('permit_dues_issue'), self.sheet_post(**over), follow=True)

    def pay(self, who=None, amount='1000000', slip='123', **over):
        post = {'amount': amount, 'date': '1405/07/26', 'slip_no': slip, 'receipt': upload('f.png', PNG)}
        post.update(over)
        return client_for(who or self.citizen).post(self.url('permit_dues_pay'), post, follow=True)


class Sheet(Step7):
    def test_the_officer_is_told_when_step_6_ends_and_the_status_waits_for_the_sheet(self):
        self.assertTrue(Notification.objects.filter(user=self.accountant, title='عوارض ساخت‌وساز بدون پروانه').exists())
        self.assertEqual(self.permit.status_text, 'منتظر محاسبه‌ی عوارض و بهای خدمات (مسئول مالی)')
        self.assertTrue(self.permit.needs_accountant_dues)

    def test_the_page_is_prefilled_from_the_visit_report_and_opens_for_the_right_people(self):
        for who in (self.accountant, self.dehyari, self.citizen, self.clerk, self.engineer):
            self.assertEqual(client_for(who).get(self.url('permit_dues')).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk):
            self.assertEqual(client_for(who).get(self.url('permit_dues')).status_code, 404, who.profile.role)
        inputs = permit_dues.sheet_inputs(self.permit)
        self.assertEqual(inputs['annual'], f'{self.permit.area_m2:g}')

    def test_only_the_officer_and_the_dehyari_issue_and_the_owner_is_told_the_total(self):
        for who in (self.citizen, self.clerk, self.engineer, self.neighbour):
            self.issue(who)
            self.assertEqual(self.reload().dues_state, '', who.profile.role)
        self.issue()
        self.assertEqual(self.reload().dues_state, 'issued')
        self.assertEqual(self.permit.dues_total, 144_704_560 + 157_696_000 + 4_400_000 + 82_830_000 + 66_264_000 + 1_100_000 + 4_400_000 + 4_400_000 + 1_100_000 + 6_988_080)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='عوارض و بهای خدمات اعلام شد').exists())
        self.assertEqual(self.permit.status_text, 'منتظر پرداخت عوارض (از متقاضی)')
        self.assertEqual(client_for(self.citizen).get(self.url('permit_dues_sheet')).status_code, 200)

    def test_bad_numbers_are_refused_and_the_sheet_is_frozen_after_a_payment(self):
        self.issue(width='99')
        self.issue(a_res_1='abc')
        self.assertEqual(self.reload().dues_state, '')
        self.issue()
        self.pay()
        before = self.reload().dues_total
        self.issue(a_res_2='1000')
        self.assertEqual(self.reload().dues_total, before)


class Payments(Step7):
    def setUp(self):
        super().setUp()
        self.issue()

    def test_a_slip_waits_for_the_staff_and_counts_once_confirmed(self):
        self.pay()
        self.assertEqual((self.reload().dues_paid, self.permit.status_text), (0, 'فیش پرداخت منتظر تایید'))
        self.assertTrue(self.permit.needs_staff)
        pid = self.permit.dues['payments'][0]['id']
        client_for(self.neighbour).post(reverse('main:permit_dues_pay_confirm', args=[self.permit.pk, pid]))
        self.assertEqual(self.reload().dues_paid, 0)
        for who in (self.accountant, self.clerk):
            client_for(who).post(reverse('main:permit_dues_pay_confirm', args=[self.permit.pk, pid]))
            self.assertEqual(self.reload().dues_paid, 1_000_000, who.profile.role)

    def test_a_payment_the_staff_record_is_confirmed_at_once_and_duplicates_are_refused(self):
        self.pay(self.accountant, amount='5000000', slip='9')
        self.assertEqual(self.reload().dues_paid, 5_000_000)
        self.pay(self.accountant, slip='9')
        self.assertEqual(len(self.reload().dues['payments']), 1)

    def test_paying_everything_settles_and_any_of_the_staff_ends_the_step(self):
        self.pay(self.accountant, amount=str(self.reload().dues_total), slip='1')
        self.assertTrue(self.reload().dues_settled)
        self.act(self.clerk, 'permit_step7_finish')
        self.assertEqual(self.reload().stage_no, 7)
        for who in (self.clerk, self.engineer, self.dehyari, self.accountant):
            self.permit.stage_no = 7
            self.permit.save()
            self.act(who, 'permit_step7_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 8, who.profile.role)

    def test_nothing_ends_before_the_fees_are_settled_and_outsiders_cannot_end_it(self):
        self.act(self.dehyari, 'permit_step7_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 7)
        self.pay(self.accountant, amount=str(self.reload().dues_total), slip='1')
        for who in (self.citizen, self.neighbour, self.stranger_clerk):
            self.act(who, 'permit_step7_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 7, who.profile.role)


class Instalments(Step7):
    def setUp(self):
        super().setUp()
        self.issue()
        self.pay(self.accountant, amount='100000000', slip='1')

    def ask(self, **over):
        post = {'count': '4', 'first_due': soon(30), 'reason': 'کم‌درآمد'}
        post.update(over)
        return client_for(self.citizen).post(self.url('permit_plan_request'), post, follow=True)

    def cheques(self, **over):
        rows = permit_dues.cheque_rows(self.reload())
        post = {'legal_id': '14001234567'}
        for i, row in enumerate(rows):
            post.update({f'c{i}_no': str(1000 + i), f'c{i}_bank': 'ملی', f'c{i}_amount': row['amount'], f'c{i}_due': row['due']})
        post.update(over)
        return client_for(self.citizen).post(self.url('permit_cheques_register'), post, follow=True)

    def go_to_signed(self):
        self.ask()
        self.act(self.clerk, 'permit_plan_approve', confirm='on')
        self.act(self.accountant, 'permit_plan_sign', confirm='on')
        self.assertEqual(self.reload().plan_state, 'signed')

    def test_the_request_needs_a_count_and_a_future_date_and_only_the_owner_asks(self):
        for bad in ({'count': '1'}, {'count': '99'}, {'count': ''}, {'first_due': '1300/01/01'}, {'first_due': 'x'}):
            self.ask(**bad)
            self.assertEqual(self.reload().plan_state, '', bad)
        for who in (self.clerk, self.accountant, self.neighbour):
            client_for(who).post(self.url('permit_plan_request'), {'count': '4', 'first_due': soon(30)})
            self.assertEqual(self.reload().plan_state, '', who.profile.role)
        self.ask()
        self.assertEqual(self.reload().plan_state, 'requested')
        self.assertTrue(self.permit.needs_staff)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='درخواست تقسیط عوارض').exists())

    def test_the_plan_splits_what_is_still_owed_into_equal_cheques(self):
        self.ask()
        rows = permit_dues.schedule(self.reload())
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(r['amount'] for r in rows), self.permit.dues_total - 100_000_000)

    def test_the_clerk_or_the_dehyari_approve_but_the_engineer_and_the_officer_do_not(self):
        self.ask()
        for who in (self.engineer, self.accountant, self.citizen, self.neighbour):
            self.act(who, 'permit_plan_approve', confirm='on')
            self.assertEqual(self.reload().plan_state, 'requested', who.profile.role)
        self.act(self.clerk, 'permit_plan_approve')
        self.assertEqual(self.reload().plan_state, 'requested')                     # the tick is needed
        self.act(self.dehyari, 'permit_plan_approve', confirm='on', count='5')
        self.assertEqual((self.reload().plan_state, permit_dues.plan(self.permit)['count']), ('approved', 5))
        self.assertTrue(Notification.objects.filter(user=self.accountant, title='تقسیط عوارض منتظر امضا').exists())

    def test_only_the_officer_signs_and_a_refusal_needs_a_reason(self):
        self.ask()
        self.act(self.clerk, 'permit_plan_return', notes='')
        self.assertEqual(self.reload().plan_state, 'requested')
        self.act(self.clerk, 'permit_plan_return', notes='چک‌ها کم است')
        self.assertEqual(self.reload().plan_state, 'returned')
        self.ask()
        self.act(self.clerk, 'permit_plan_approve', confirm='on')
        for who in (self.clerk, self.engineer, self.citizen):
            self.act(who, 'permit_plan_sign', confirm='on')
            self.assertEqual(self.reload().plan_state, 'approved', who.profile.role)
        self.act(self.accountant, 'permit_plan_sign', confirm='on')
        self.assertEqual(self.reload().plan_state, 'signed')

    def test_the_cheques_need_the_legal_id_the_right_total_and_ordered_dates(self):
        self.go_to_signed()
        self.cheques(legal_id='123')
        self.assertEqual(self.reload().plan_state, 'signed')
        self.cheques(c0_amount='1')
        self.assertEqual(self.reload().plan_state, 'signed')
        self.cheques(c1_due=permit_dues.cheque_rows(self.permit)[0]['due'])
        self.assertEqual(self.reload().plan_state, 'signed')
        self.cheques(c1_no='1000')
        self.assertEqual(self.reload().plan_state, 'signed')
        self.cheques(c2_bank='')
        self.assertEqual(self.reload().plan_state, 'signed')
        self.cheques()
        self.assertEqual(self.reload().plan_state, 'registered')
        self.assertEqual(permit_dues.plan(self.permit)['legal_id'], '14001234567')
        self.assertTrue(Notification.objects.filter(user=self.accountant, title='ثبت چک‌های عوارض').exists())

    def test_the_officer_confirms_the_registration_and_the_fees_count_as_settled(self):
        self.go_to_signed()
        self.cheques()
        for who in (self.clerk, self.citizen, self.engineer):
            self.act(who, 'permit_cheques_confirm', confirm='on')
            self.assertEqual(self.reload().plan_state, 'registered', who.profile.role)
        self.act(self.accountant, 'permit_cheques_confirm')
        self.assertEqual(self.reload().plan_state, 'registered')
        self.act(self.accountant, 'permit_cheques_confirm', confirm='on')
        self.assertEqual(self.reload().plan_state, 'confirmed')
        self.assertTrue(self.permit.dues_settled)
        self.act(self.dehyari, 'permit_step7_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 8)

    def test_the_officer_can_send_the_cheques_back_and_new_slips_are_refused_after_registration(self):
        self.go_to_signed()
        self.cheques()
        self.pay(self.accountant, amount='5', slip='77')
        self.assertEqual(len(self.reload().dues['payments']), 1)
        self.act(self.accountant, 'permit_cheques_return', notes='')
        self.assertEqual(self.reload().plan_state, 'registered')
        self.act(self.accountant, 'permit_cheques_return', notes='شماره‌ی چک دوم اشتباه است')
        self.assertEqual(self.reload().plan_state, 'signed')
        self.cheques()
        self.assertEqual(self.reload().plan_state, 'registered')

    def test_the_accountants_list_shows_the_file(self):
        from main.office import permits as office_permits
        rows = office_permits.fee_rows_for(self.accountant)
        self.assertIn(self.permit.pk, [f.pk for f in rows['rows']])
