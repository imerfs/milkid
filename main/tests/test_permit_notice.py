"""Construction without a permit, step 3: the warning notice the owner already received (uploaded, checked, confirmed)."""
import datetime

import jdatetime
from django.urls import reverse

from main.models import Notification, PermitDocument, PermitFile
from main.tests.helpers import client_for
from main.tests.test_permit_files import PDF, PNG, Village, upload
from main.tests.test_permit_unlicensed import CODE, sign_defence, unlicensed


def soon(days=10):
    return (jdatetime.date.today() + datetime.timedelta(days=days)).strftime('%Y/%m/%d')


def notice_post(**override):
    data = {'scan': upload('notice.png', PNG), 'number': '2/4493', 'date': '1402/10/18', 'addressee': 'علی رضایی',
            'position': 'inside', 'delivery': 'handed'}
    data.update(override)
    return {k: v for k, v in data.items() if v is not None}


class Notice(Village):
    def setUp(self):
        super().setUp()
        self.permit = self.new_file()

    def new_file(self):
        """A file of the unlicensed track that reached step 3 (step 1 confirmed, step 2 papers confirmed)."""
        client_for(self.citizen).post(reverse('main:without_permit_form'), unlicensed())
        permit = PermitFile.objects.latest('pk')
        sign_defence(self.citizen, permit)
        client_for(self.clerk).post(reverse('main:permit_open', args=[permit.pk]), {'renewal_code': CODE})
        client_for(self.citizen).post(reverse('main:permit_commission_upload', args=[permit.pk]),
                                      {'request_scan': upload('r.png', PNG), 'undertaking_scan': upload('u.png', PNG), 'signed': 'on'})
        client_for(self.dehyari).post(reverse('main:permit_commission_verify', args=[permit.pk]), {'confirm': 'on'})
        permit.refresh_from_db()
        self.assertEqual(permit.stage_no, 3)
        return permit

    def reload(self):
        self.permit.refresh_from_db()
        return self.permit

    def url(self, name='permit_notice'):
        return reverse(f'main:{name}', args=[self.permit.pk])

    def send(self, who=None, **override):
        return client_for(who or self.citizen).post(self.url('permit_notice_upload'), notice_post(**override), follow=True)

    def decide(self, who, name='permit_notice_verify', **post):
        return client_for(who).post(self.url(name), post, follow=True)


class Page(Notice):
    def test_the_owner_and_staff_open_it_and_nobody_else(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url()).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url()).status_code, 404, who.profile.role)
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_it_asks_the_owner_for_the_notice_and_names_the_owner_on_it(self):
        page = client_for(self.citizen).get(self.url()).content.decode()
        self.assertIn('اخطاریه دارم', page)
        self.assertIn('درخواست دریافت اخطاریه', page)
        self.assertIn('value="علی رضایی"', page)
        self.assertEqual(self.permit.status_text, 'منتظر اخطاریه‌ی قبلی یا درخواست صدور اخطاریه (از متقاضی)')

    def test_the_page_is_closed_before_step_three_and_to_permit_files(self):
        client_for(self.citizen).post(reverse('main:without_permit_form'), unlicensed())
        fresh = PermitFile.objects.latest('pk')
        self.assertEqual(client_for(self.citizen).get(reverse('main:permit_notice', args=[fresh.pk])).status_code, 302)
        permit = Village.filed(self)
        self.assertEqual(client_for(self.citizen).get(reverse('main:permit_notice', args=[permit.pk])).status_code, 404)

    def test_the_file_page_links_to_it(self):
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(self.url(), page)


class Uploading(Notice):
    def test_the_scan_and_the_figures_go_to_the_staff(self):
        self.send()
        permit = self.reload()
        self.assertEqual((permit.notice_state, permit.stage_no), ('uploaded', 3))
        self.assertEqual((permit.notice['number'], permit.notice['date'], permit.notice['position'], permit.notice['delivery']),
                         ('2/4493', '1402/10/18', 'inside', 'handed'))
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='warning_notice').count(), 1)
        self.assertTrue(permit.needs_staff)
        self.assertEqual(permit.status_text, 'اخطاریه منتظر تایید')
        for staff in (self.clerk, self.engineer):
            self.assertTrue(Notification.objects.filter(user=staff, title='اخطاریه‌ی مالک رسید').exists())

    def test_every_figure_and_the_scan_are_needed(self):
        for override in ({'scan': None}, {'number': ''}, {'date': ''}, {'date': '1402/13/40'}, {'date': '1499/01/01'},
                         {'addressee': ''}, {'position': ''}, {'position': 'x'}, {'delivery': ''}, {'delivery': 'x'}):
            self.send(**override)
            self.assertEqual(self.reload().notice_state, '', override)
        self.assertFalse(PermitDocument.objects.filter(file=self.permit, kind='warning_notice').exists())

    def test_a_wrong_file_type_is_refused(self):
        self.send(scan=upload('x.exe', b'MZ....'))
        self.assertEqual(self.reload().notice_state, '')

    def test_only_the_owner_sends_and_only_once(self):
        self.send(who=self.clerk)
        self.assertEqual(self.reload().notice_state, '')
        self.send()
        self.send(number='999')
        self.assertEqual(self.reload().notice['number'], '2/4493')

    def test_the_scan_is_served_to_the_owner_and_staff_only(self):
        self.send()
        doc = PermitDocument.objects.get(file=self.permit, kind='warning_notice')
        url = reverse('main:permit_document', args=[doc.pk])
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(url).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(url).status_code, 404, who.profile.role)


class Deciding(Notice):
    def setUp(self):
        super().setUp()
        self.send()

    def good(self, **override):
        return {'confirm': 'on', 'number': '2/4493', 'date': '1402/10/18', 'addressee': 'علی رضایی', 'position': 'inside',
                'delivery': 'handed', 'notes': 'مطابق اصل', **override}

    def test_the_clerk_the_expert_and_the_dehyari_each_can_confirm(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            if who != self.clerk:
                self.permit = self.new_file()
                self.send()
            self.decide(who, **self.good())
            permit = self.reload()
            self.assertEqual((permit.notice_state, permit.stage_no, permit.state), ('verified', 3, 'done'), who.profile.role)       # the visit follows
            self.assertEqual(permit.notice['checked']['by'], who.username)
            self.assertTrue(Notification.objects.filter(user=self.citizen, title='اخطاریه‌ی شما تایید شد').exists())

    def test_the_tick_is_needed_and_the_rest_cannot_decide(self):
        self.decide(self.clerk, **self.good(confirm=''))
        self.assertEqual(self.reload().notice_state, 'uploaded')
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.decide(who, **self.good())
            self.assertEqual(self.reload().notice_state, 'uploaded', who.profile.role)

    def test_the_staff_may_correct_a_figure_while_confirming(self):
        self.decide(self.engineer, **self.good(number='2/4494', delivery='posted'))
        permit = self.reload()
        self.assertEqual((permit.notice['number'], permit.notice['delivery']), ('2/4494', 'posted'))

    def test_the_comparison_flags_a_name_that_does_not_match_and_a_number_used_before(self):
        page = client_for(self.clerk).get(self.url()).content.decode()
        self.assertIn('نام روی اخطاریه با مالک پرونده می‌خواند', page)
        self.assertIn('شماره‌ی اخطاریه در پرونده‌ی دیگری نیست', page)
        other = self.new_file()
        client_for(self.citizen).post(reverse('main:permit_notice_upload', args=[other.pk]), notice_post(addressee='کس دیگر'))
        self.permit = other
        page = client_for(self.clerk).get(self.url()).content.decode()
        self.assertIn('نمی‌خواند', page)
        self.assertIn('همین شماره‌ی اخطاریه در پرونده‌ی دیگری هم ثبت شده است', page)

    def test_sending_back_needs_a_reason_and_the_owner_may_keep_the_old_scan(self):
        self.decide(self.engineer, 'permit_notice_return', notes='')
        self.assertEqual(self.reload().notice_state, 'uploaded')
        self.decide(self.engineer, 'permit_notice_return', notes='تاریخ ناخوانا است')
        self.assertEqual(self.reload().notice_state, 'returned')
        self.assertIn('تاریخ ناخوانا است', client_for(self.citizen).get(self.url()).content.decode())
        old = PermitDocument.objects.get(file=self.permit, kind='warning_notice').pk
        self.send(scan=None, date='1402/10/19')
        permit = self.reload()
        self.assertEqual((permit.notice_state, permit.notice['date']), ('uploaded', '1402/10/19'))
        self.assertEqual(PermitDocument.objects.get(file=permit, kind='warning_notice').pk, old)
        self.send(scan=upload('new.png', PNG), date='1402/10/19')                 # sent already: refused
        self.assertEqual(PermitDocument.objects.get(file=permit, kind='warning_notice').pk, old)

    def test_after_confirming_the_notice_the_owner_asks_for_the_visit_and_step_four_opens(self):
        self.decide(self.dehyari, **self.good())
        permit = self.reload()
        self.assertEqual(permit.status_text, 'منتظر درخواست بازدید (از متقاضی)')
        self.assertFalse(permit.needs_staff)
        self.send(number='555')
        self.assertEqual(self.reload().notice['number'], '2/4493')
        client_for(self.citizen).post(self.url('permit_visit_request'), {'date': '1300/01/01', 'slot': 'morning'})
        client_for(self.engineer).post(self.url('permit_visit_complete'), {'confirm': 'on'})
        self.assertEqual(self.reload().stage_no, 3)                # nothing was requested: nothing to complete
        client_for(self.citizen).post(self.url('permit_visit_request'), {'date': soon(), 'slot': 'morning', 'note': 'هماهنگ شده'})
        client_for(self.engineer).post(self.url('permit_visit_complete'), {'confirm': 'on', 'notes': 'سه طبقه، نمای ناتمام'})
        permit = self.reload()
        self.assertEqual((permit.visit_state, permit.stage_no), ('done', 4))
        self.assertEqual(permit.status_text, 'منتظر گزارش بازدید (کارشناس فنی)')
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[permit.pk])).content.decode()
        self.assertIn(reverse('main:permit_report', args=[permit.pk]), page)
