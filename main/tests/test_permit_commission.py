"""Construction without a permit, step 2: the request form and the undertaking (filled, signed on paper, uploaded, confirmed)."""
from django.urls import reverse

from main.models import Notification, PermitDocument, PermitFile
from main.tests.helpers import client_for
from main.tests.test_permit_files import PDF, PNG, Village, upload
from main.tests.test_permit_unlicensed import CODE, sign_defence, unlicensed


class Commission(Village):
    def setUp(self):
        super().setUp()
        response = client_for(self.citizen).post(reverse('main:without_permit_form'), unlicensed())
        self.assertEqual(response.status_code, 302)
        self.permit = PermitFile.objects.latest('pk')
        sign_defence(self.citizen, self.permit)
        client_for(self.clerk).post(reverse('main:permit_open', args=[self.permit.pk]), {'renewal_code': CODE})
        self.reload()

    def reload(self):
        self.permit.refresh_from_db()
        return self.permit

    def url(self, name='permit_commission'):
        return reverse(f'main:{name}', args=[self.permit.pk])

    def send(self, who=None, **extra):
        data = {'request_scan': upload('req.png', PNG), 'undertaking_scan': upload('und.pdf', PDF), 'signed': 'on', **extra}
        data = {k: v for k, v in data.items() if v is not None}
        return client_for(who or self.citizen).post(self.url('permit_commission_upload'), data, follow=True)

    def decide(self, who, name='permit_commission_verify', **post):
        return client_for(who).post(self.url(name), post, follow=True)


class Page(Commission):
    def test_the_owner_sees_both_forms_filled_from_the_file(self):
        page = client_for(self.citizen).get(self.url())
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn('value="علی رضایی"', body)
        self.assertIn('value="حسن"', body)
        self.assertIn('فرم درخواست', body)
        self.assertIn('تعهدنامه', body)
        self.assertIn('pcm-data', body)
        self.assertEqual(page.context['d']['form']['phone'], '09121234567')

    def test_staff_see_it_too_but_nobody_else(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url()).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url()).status_code, 404, who.profile.role)
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_a_permit_track_file_has_no_such_page(self):
        permit = Village.filed(self)
        self.assertEqual(permit.track, 'permit')
        self.assertEqual(client_for(self.citizen).get(reverse('main:permit_commission', args=[permit.pk])).status_code, 404)

    def test_before_step_one_is_confirmed_the_page_is_not_open(self):
        client_for(self.citizen).post(reverse('main:without_permit_form'), unlicensed())
        fresh = PermitFile.objects.latest('pk')
        self.assertEqual(fresh.stage_no, 1)
        response = client_for(self.citizen).get(reverse('main:permit_commission', args=[fresh.pk]))
        self.assertEqual(response.status_code, 302)

    def test_the_file_page_links_to_it_at_step_two(self):
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(self.url(), page)
        self.assertIn('مرحله‌ی ۲', page)


class Saving(Commission):
    def test_the_owner_corrects_the_values(self):
        client_for(self.citizen).post(self.url('permit_commission_save'), {
            'name': 'علی رضایی', 'father': 'محمد', 'id_number': '٧٣٣', 'national_id': self.permit.people.first().national_id,
            'street': 'همت ۶', 'phone': '09155550000', 'date': '۱۴۰۵/۰۶/۲۲'})
        form = self.reload().commission['form']
        self.assertEqual((form['father'], form['id_number'], form['street'], form['date']), ('محمد', '733', 'همت ۶', '1405/06/22'))
        page = client_for(self.citizen).get(self.url()).content.decode()
        self.assertIn('value="همت ۶"', page)

    def test_bad_values_are_refused_and_nothing_changes(self):
        good = {'name': 'علی رضایی', 'father': 'حسن', 'id_number': '1', 'national_id': self.permit.people.first().national_id,
                'street': 'x', 'phone': '09121234567', 'date': '1405/06/22'}
        for field, value in (('national_id', '1234567890'), ('phone', '123'), ('date', '1405/13/40'), ('name', '')):
            client_for(self.citizen).post(self.url('permit_commission_save'), {**good, field: value})
            self.assertEqual(self.reload().commission, {}, field)

    def test_the_staff_may_correct_it_for_a_walk_in_owner_and_the_neighbour_may_not(self):
        data = {'name': 'علی رضایی', 'father': 'اکبر', 'id_number': '5', 'national_id': self.permit.people.first().national_id,
                'street': 'y', 'phone': '09121234567', 'date': '1405/06/22'}
        client_for(self.neighbour).post(self.url('permit_commission_save'), data)
        self.assertEqual(self.reload().commission, {})
        client_for(self.clerk).post(self.url('permit_commission_save'), data)
        self.assertEqual(self.reload().commission['form']['father'], 'اکبر')


class Uploading(Commission):
    def test_both_signed_scans_go_to_the_staff(self):
        self.send()
        permit = self.reload()
        self.assertEqual((permit.commission_state, permit.stage_no), ('uploaded', 2))
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='comm_request').count(), 1)
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='comm_undertake').count(), 1)
        self.assertTrue(permit.needs_staff)
        self.assertEqual(permit.status_text, 'فرم درخواست و تعهدنامه منتظر تایید')
        for staff in (self.clerk, self.engineer):
            self.assertTrue(Notification.objects.filter(user=staff, title='فرم‌های امضاشده رسید').exists())

    def test_both_papers_and_the_signing_tick_are_needed(self):
        self.send(undertaking_scan=None)
        self.send(request_scan=None)
        self.send(signed=None)
        self.assertEqual(self.reload().commission_state, '')
        self.assertFalse(PermitDocument.objects.filter(file=self.permit, kind__in=('comm_request', 'comm_undertake')).exists())

    def test_a_wrong_file_type_is_refused(self):
        self.send(request_scan=upload('x.exe', b'MZ....'))
        self.assertEqual(self.reload().commission_state, '')

    def test_only_the_owner_sends_and_only_once(self):
        self.send(who=self.clerk)
        self.assertEqual(self.reload().commission_state, '')
        self.send()
        self.send()                                  # already sent: refused
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='comm_request').count(), 1)

    def test_the_scans_are_served_to_the_owner_and_the_staff_only(self):
        self.send()
        doc = PermitDocument.objects.get(file=self.permit, kind='comm_request')
        url = reverse('main:permit_document', args=[doc.pk])
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(url).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(url).status_code, 404, who.profile.role)


class Deciding(Commission):
    def setUp(self):
        super().setUp()
        self.send()

    def test_the_clerk_the_expert_and_the_dehyari_each_can_confirm(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            if who != self.clerk:
                client_for(self.citizen).post(reverse('main:without_permit_form'), unlicensed())
                self.permit = PermitFile.objects.latest('pk')
                sign_defence(self.citizen, self.permit)
                client_for(self.clerk).post(reverse('main:permit_open', args=[self.permit.pk]), {'renewal_code': CODE})
                self.send()
            self.decide(who, confirm='on', notes='خوانا بود')
            permit = self.reload()
            self.assertEqual((permit.commission_state, permit.stage_no, permit.state), ('verified', 3, 'done'), who.profile.role)
            self.assertEqual(permit.commission['checked']['by'], who.username)
            self.assertTrue(Notification.objects.filter(user=self.citizen, title='فرم‌های شما تایید شد').exists())

    def test_the_tick_is_needed_and_the_rest_cannot_decide(self):
        self.decide(self.clerk)
        self.assertEqual(self.reload().commission_state, 'uploaded')
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.decide(who, confirm='on')
            self.assertEqual(self.reload().commission_state, 'uploaded', who.profile.role)

    def test_sending_back_needs_a_reason_and_the_owner_replaces_only_that_paper(self):
        self.decide(self.engineer, name='permit_commission_return', notes='')
        self.assertEqual(self.reload().commission_state, 'uploaded')
        self.decide(self.engineer, name='permit_commission_return', notes='تعهدنامه امضا ندارد')
        permit = self.reload()
        self.assertEqual(permit.commission_state, 'returned')
        self.assertIn('تعهدنامه امضا ندارد', client_for(self.citizen).get(self.url()).content.decode())
        old_request = PermitDocument.objects.get(file=permit, kind='comm_request').pk
        self.send(request_scan=None, undertaking_scan=upload('new.png', PNG))
        permit = self.reload()
        self.assertEqual(permit.commission_state, 'uploaded')
        self.assertEqual(PermitDocument.objects.get(file=permit, kind='comm_request').pk, old_request)
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='comm_undertake').count(), 1)
        self.assertEqual(PermitDocument.objects.get(file=permit, kind='comm_undertake').original_name, 'new.png')

    def test_after_confirming_the_forms_are_locked_and_step_three_opens(self):
        self.decide(self.dehyari, confirm='on')
        self.assertEqual(self.reload().status_text, 'منتظر اخطاریه‌ی قبلی یا درخواست صدور اخطاریه (از متقاضی)')
        client_for(self.citizen).post(self.url('permit_commission_save'), {'name': 'کس دیگر', 'national_id': self.permit.people.first().national_id,
                                                                            'date': '1405/01/01'})
        self.assertEqual(self.reload().commission.get('form', {}).get('name'), None)
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(reverse('main:permit_notice', args=[self.permit.pk]), page)


class SubjectAndAddressee(Commission):
    def test_the_request_defaults_to_the_usual_subject_addressed_to_the_council(self):
        form = client_for(self.citizen).get(self.url()).context['d']['form']
        self.assertEqual(form['subject'], 'تشکیل پرونده کمیسیون و تقسیط هزینه‌های دهیاری و جریمه کمیسیون')
        self.assertEqual(form['addressee'], 'council')
        page = client_for(self.citizen).get(self.url()).content.decode()
        self.assertIn('شورای اسلامی روستا', page)

    def test_the_owner_may_change_both_and_a_bad_addressee_falls_back(self):
        base = {'name': 'علی رضایی', 'father': 'حسن', 'id_number': '1', 'national_id': self.permit.people.first().national_id,
                'street': 'x', 'phone': '09121234567', 'date': '1405/06/22'}
        client_for(self.citizen).post(self.url('permit_commission_save'), {**base, 'subject': 'تقسیط جریمه', 'addressee': 'dehyari'})
        form = self.reload().commission['form']
        self.assertEqual((form['subject'], form['addressee']), ('تقسیط جریمه', 'dehyari'))
        client_for(self.citizen).post(self.url('permit_commission_save'), {**base, 'subject': '', 'addressee': 'x'})
        form = self.reload().commission['form']
        self.assertEqual((form['subject'], form['addressee']), ('تشکیل پرونده کمیسیون و تقسیط هزینه‌های دهیاری و جریمه کمیسیون', 'council'))
