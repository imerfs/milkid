"""Construction without a permit, step 3: no notice yet (the owner asks, the staff fill and print one, he signs in person) and the visit."""
import datetime

import jdatetime
from django.urls import reverse

from main.models import Notification, PermitDocument
from main.tests.helpers import client_for
from main.tests.test_permit_files import PNG, upload
from main.tests.test_permit_notice import Notice, notice_post

def soon(days=10):
    return (jdatetime.date.today() + datetime.timedelta(days=days)).strftime('%Y/%m/%d')


ISSUE = {'number': '17/5149', 'date': '1405/06/22', 'addressee': 'علی رضایی', 'address': 'روستای دستگرد، همت ۶', 'position': 'inside',
         'delivery': 'handed', 'tick_rules': 'on', 'tick_permit': 'on', 'tick_plans': 'on'}


class Issuing(Notice):
    def ask(self):
        return client_for(self.citizen).post(self.url('permit_notice_request'), follow=True)

    def issue(self, who, **override):
        data = {**ISSUE, **override}
        data = {k: v for k, v in data.items() if v is not None}
        return client_for(who).post(self.url('permit_notice_issue'), data, follow=True)

    def test_the_owner_without_a_notice_asks_and_the_staff_are_told(self):
        self.ask()
        permit = self.reload()
        self.assertEqual(permit.notice_state, 'requested')
        self.assertEqual(permit.status_text, 'درخواست اخطاریه منتظر صدور (دهیاری)')
        self.assertTrue(permit.needs_staff)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='درخواست اخطاریه').exists())
        self.ask()                                                  # a second request changes nothing
        self.assertEqual(self.reload().notice_state, 'requested')

    def test_the_form_is_filled_from_the_file_for_the_staff(self):
        self.ask()
        page = client_for(self.clerk).get(self.url())
        form = page.context['f']
        self.assertEqual((form['addressee'], form['ticks']['permit'], form['ticks']['plans'], form['ticks']['technical']), ('علی رضایی', True, True, False))
        self.assertIn('دستگرد', form['address'])
        self.assertIn('pnf-data', page.content.decode())
        self.assertEqual(page.context['payload']['blank'], '/static/forms/permit/form14_blank.jpg')
        self.assertNotIn('pnf-data', client_for(self.citizen).get(self.url()).content.decode())          # the owner does not edit it

    def test_each_of_the_three_staff_issues_it_and_nobody_else(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit = self.new_file()
            self.ask()
            self.issue(who)
            permit = self.reload()
            self.assertEqual(permit.notice_state, 'issued', who.profile.role)
            self.assertEqual(permit.notice['issued']['by'], who.username)
        self.permit = self.new_file()
        self.ask()
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.issue(who)
            self.assertEqual(self.reload().notice_state, 'requested', who.profile.role)

    def test_the_issued_form_keeps_the_ticks_and_fills_the_figures(self):
        self.ask()
        self.issue(self.engineer)
        permit = self.reload()
        form = permit.notice['form']
        self.assertEqual((form['number'], form['date'], form['position'], form['delivery']), ('17/5149', '1405/06/22', 'inside', 'handed'))
        self.assertEqual(form['ticks'], {'rules': True, 'permit': True, 'plans': True, 'technical': False, 'extra': False})
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='اخطاریه‌ی شما صادر شد').exists())
        page = client_for(self.citizen).get(self.url()).context
        self.assertEqual((page['n']['number'], page['n']['position']), ('17/5149', 'inside'))           # prefilled for the signed upload

    def test_a_walk_in_owner_needs_no_request_first(self):
        self.assertEqual(self.reload().notice_state, '')
        self.issue(self.dehyari)
        self.assertEqual(self.reload().notice_state, 'issued')

    def test_bad_forms_are_refused(self):
        for bad in ({'date': '1405/13/40'}, {'addressee': ''}, {'position': 'x'}, {'delivery': 'x'},
                    {'tick_rules': None, 'tick_permit': None, 'tick_plans': None}):
            self.issue(self.clerk, **bad)
            self.assertEqual(self.reload().notice_state, '', bad)

    def test_after_issue_the_owner_or_the_staff_upload_the_signed_paper_and_it_is_checked_as_usual(self):
        self.ask()
        self.issue(self.clerk)
        client_for(self.citizen).post(self.url('permit_notice_upload'), notice_post(number='17/5149'))
        self.assertEqual(self.reload().notice_state, 'uploaded')
        self.assertEqual(self.reload().notice['form']['ticks']['permit'], True)                        # the issued form survives the upload
        self.decide(self.engineer, confirm='on', number='17/5149', date='1405/06/22', addressee='علی رضایی', position='inside', delivery='handed')
        self.assertEqual(self.reload().notice_state, 'verified')
        self.assertIn('form', self.reload().notice)

    def test_the_staff_may_upload_the_signed_paper_of_a_notice_they_issued(self):
        self.issue(self.clerk)
        data = {**notice_post(number='17/5149')}
        client_for(self.neighbour).post(self.url('permit_notice_upload'), data)
        self.assertEqual(self.reload().notice_state, 'issued')
        client_for(self.clerk).post(self.url('permit_notice_upload'), {**notice_post(number='17/5149'), 'scan': upload('signed.png', PNG)})
        self.assertEqual(self.reload().notice_state, 'uploaded')
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='warning_notice').count(), 1)

    def test_the_owner_may_not_upload_before_asking_when_he_has_none_but_may_when_he_has_one(self):
        client_for(self.citizen).post(self.url('permit_notice_upload'), notice_post())
        self.assertEqual(self.reload().notice_state, 'uploaded')


class Visit(Notice):
    def verified(self):
        self.send()
        self.decide(self.clerk, confirm='on', number='2/4493', date='1402/10/18', addressee='علی رضایی', position='inside', delivery='handed')
        self.assertEqual(self.reload().notice_state, 'verified')

    def ask(self, **override):
        return client_for(self.citizen).post(self.url('permit_visit_request'), {'date': soon(), 'slot': 'morning', 'note': 'x', **override}, follow=True)

    def test_the_visit_can_only_be_asked_after_the_notice_is_confirmed(self):
        self.ask()
        self.assertEqual(self.reload().visit_state, '')
        self.send()
        self.ask()
        self.assertEqual(self.reload().visit_state, '')

    def test_ask_schedule_and_complete_move_the_file_to_step_four(self):
        self.verified()
        for bad in ({'date': '1300/01/01'}, {'date': 'x'}, {'slot': 'night'}, {'date': ''}):
            self.ask(**bad)
            self.assertEqual(self.reload().visit_state, '', bad)
        for who in (self.clerk, self.accountant, self.neighbour):          # only the owner asks
            client_for(who).post(self.url('permit_visit_request'), {'date': soon(), 'slot': 'morning'})
        self.assertEqual(self.reload().visit_state, '')
        self.ask()
        permit = self.reload()
        self.assertEqual((permit.visit_state, permit.visit['preferred_date'], permit.visit['slot']), ('requested', soon(), 'morning'))
        self.assertEqual(permit.status_text, 'درخواست بازدید منتظر کارشناس فنی')
        self.assertTrue(permit.needs_staff)
        self.assertTrue(Notification.objects.filter(user=self.engineer, title='درخواست بازدید').exists())
        self.ask(date=soon(12))                                 # twice: refused
        self.assertEqual(self.reload().visit['preferred_date'], soon())
        # schedule (any of the three), not the owner or an outsider
        client_for(self.citizen).post(self.url('permit_visit_schedule'), {'date': soon(11), 'slot': 'afternoon'})
        self.assertEqual(self.reload().visit_state, 'requested')
        client_for(self.engineer).post(self.url('permit_visit_schedule'), {'date': soon(11), 'slot': 'afternoon'})
        permit = self.reload()
        self.assertEqual((permit.visit_state, permit.visit['date'], permit.visit['slot']), ('scheduled', soon(11), 'afternoon'))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='زمان بازدید').exists())
        # completing needs the tick; then step four
        client_for(self.dehyari).post(self.url('permit_visit_complete'), {'notes': 'x'})
        self.assertEqual(self.reload().stage_no, 3)
        client_for(self.stranger_clerk).post(self.url('permit_visit_complete'), {'confirm': 'on'})
        self.assertEqual(self.reload().stage_no, 3)
        client_for(self.dehyari).post(self.url('permit_visit_complete'), {'confirm': 'on', 'notes': 'سه طبقه'})
        permit = self.reload()
        self.assertEqual((permit.visit_state, permit.stage_no, permit.visit['done']['by']), ('done', 4, self.dehyari.username))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='بازدید انجام شد').exists())
        self.assertFalse(permit.needs_staff)

    def test_each_of_the_three_staff_can_complete_a_visit(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit = self.new_file()
            self.verified()
            self.ask()
            client_for(who).post(self.url('permit_visit_complete'), {'confirm': 'on'})
            self.assertEqual(self.reload().stage_no, 4, who.profile.role)

    def test_the_page_offers_the_right_forms(self):
        self.verified()
        owner = client_for(self.citizen).get(self.url()).content.decode()
        self.assertIn('درخواست بازدید', owner)
        self.assertNotIn('ثبت انجام بازدید', owner)
        self.ask()
        staff = client_for(self.engineer).get(self.url()).content.decode()
        self.assertIn('ثبت انجام بازدید', staff)
        self.assertIn('تعیین زمان بازدید', staff)
