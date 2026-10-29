"""Construction without a permit, step 1: the defence form, the shamim sketch, and the gate on confirming the step."""
from django.urls import reverse

from main.models import Notification, PermitDocument, PermitFile
from main.tests.helpers import client_for
from main.tests.test_permit_files import PNG, Village, upload
from main.tests.test_permit_unlicensed import CODE, sign_defence, unlicensed


class Step1(Village):
    def setUp(self):
        super().setUp()
        self.permit = self.file_it()

    def file_it(self, no_shamim=False):
        data = unlicensed()
        if no_shamim:
            data.pop('shamim')
            data['shamim_request'] = 'on'
        response = client_for(self.citizen).post(reverse('main:without_permit_form'), data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['errors'])
        return PermitFile.objects.latest('pk')

    def url(self, name, permit=None):
        return reverse(f'main:{name}', args=[(permit or self.permit).pk])

    def reload(self, permit=None):
        permit = permit or self.permit
        permit.refresh_from_db()
        return permit

    def open_as(self, who, permit=None):
        return client_for(who).post(self.url('permit_open', permit), {'renewal_code': CODE}, follow=True)


class DefenceForm(Step1):
    def test_the_form_is_filled_from_the_file_and_the_owner_can_change_it(self):
        page = client_for(self.citizen).get(self.url('permit_defence'))
        self.assertEqual(page.status_code, 200)
        form = page.context['d']['form']
        self.assertEqual((form['name'], form['father'], form['phone'], form['area'], form['status']),
                         ('علی رضایی', 'حسن', '09121234567', '70.28', 'without'))
        self.assertIn('pdf-data', page.content.decode())
        saved = client_for(self.citizen).post(self.url('permit_defence_save'), {
            **{k: form[k] for k in form}, 'explanation': 'از موارد قانونی اطلاعی نداشتم.', 'status': 'over', 'area': '٧٠٫٢٨', 'date': '۱۴۰۵/۰۶/۲۲'})
        self.assertEqual(saved.status_code, 302)
        stored = self.reload().defence
        self.assertEqual((stored['status'], stored['area'], stored['date'], stored['explanation']),
                         ('over', '70.28', '1405/06/22', 'از موارد قانونی اطلاعی نداشتم.'))
        self.assertEqual(client_for(self.citizen).get(self.url('permit_defence')).context['d']['form']['status'], 'over')

    def test_bad_values_change_nothing(self):
        base = {'name': 'علی رضایی', 'father': 'حسن', 'phone': '09121234567', 'village': 'دستگرد', 'district': 'مرکزی', 'county': 'بیرجند',
                'area': '70', 'status': 'without', 'explanation': '', 'date': '1405/06/22', 'dehyari': ''}
        for field, value in (('name', ''), ('phone', '123'), ('status', 'x'), ('area', '-4'), ('date', '1405/13/01')):
            client_for(self.citizen).post(self.url('permit_defence_save'), {**base, field: value})
            self.assertEqual(self.reload().defence, {}, field)

    def test_the_signed_scan_is_uploaded_and_replaced_and_only_by_the_owner(self):
        client_for(self.clerk).post(self.url('permit_defence_upload'), {'scan': upload('x.png', PNG)})
        self.assertFalse(PermitDocument.objects.filter(file=self.permit, kind='defence_form').exists())
        sign_defence(self.citizen, self.permit)
        sign_defence(self.citizen, self.permit)                          # again: replaces the first
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='defence_form').count(), 1)
        bad = client_for(self.citizen).post(self.url('permit_defence_upload'), {'scan': upload('x.exe', b'MZ..')})
        self.assertIn(bad.status_code, (302, 400))            # the upload guard or the form's own check refuses it
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='defence_form').count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='فرم دفاعیه رسید').exists())

    def test_the_page_is_for_the_owner_and_the_villages_staff_only(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_defence')).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url('permit_defence')).status_code, 404, who.profile.role)
        self.assertEqual(client_for(self.neighbour).post(self.url('permit_defence_save'), {'name': 'x'}).status_code, 404)

    def test_a_permit_track_file_has_no_defence_page(self):
        permit = Village.filed(self)
        self.assertEqual(client_for(self.citizen).get(self.url('permit_defence', permit)).status_code, 404)

    def test_the_file_page_links_to_it_and_says_what_is_missing(self):
        page = client_for(self.citizen).get(self.url('permit_file')).content.decode()
        self.assertIn(self.url('permit_defence'), page)
        self.assertEqual(self.permit.status_text, 'منتظر فرم دفاعیه‌ی امضاشده (از متقاضی)')
        sign_defence(self.citizen, self.permit)
        self.assertEqual(self.reload().status_text, 'در انتظار بررسی')


class TheGate(Step1):
    def test_step_one_cannot_be_confirmed_without_the_signed_defence_form(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.open_as(who)
            permit = self.reload()
            self.assertEqual((permit.stage_no, permit.state), (1, 'submitted'), who.profile.role)
        page = self.open_as(self.clerk).content.decode()
        self.assertIn('فرم دفاعیه‌ی امضاشده', page)

    def test_with_the_form_each_of_the_three_staff_can_confirm(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            permit = self.file_it()
            sign_defence(self.citizen, permit)
            self.open_as(who, permit)
            permit = self.reload(permit)
            self.assertEqual((permit.stage_no, permit.state, permit.opened_by), (2, 'done', who), who.profile.role)

    def test_without_a_shamim_file_the_step_waits_for_the_sketch(self):
        permit = self.file_it(no_shamim=True)
        sign_defence(self.citizen, permit)
        self.open_as(self.dehyari, permit)
        self.assertEqual((self.reload(permit).stage_no, self.reload(permit).state), (1, 'submitted'))


class SketchFlow(Step1):
    def setUp(self):
        super().setUp()
        self.permit = self.file_it(no_shamim=True)

    def act(self, who, name, **data):
        return client_for(who).post(self.url(name), data, follow=True)

    def test_request_fee_payment_and_delivery_make_the_sketch_the_shamim_file(self):
        self.assertEqual(self.permit.sketch_state, 'requested')
        self.assertTrue(self.permit.needs_staff)
        # the owner cannot set the fee, a clerk and an accountant cannot either
        for who in (self.citizen, self.clerk, self.accountant):
            self.act(who, 'permit_sketch_fee', fee='500000')
            self.assertEqual(self.reload().sketch_state, 'requested', who.profile.role)
        self.act(self.engineer, 'permit_sketch_fee', fee='۵۰۰٬۰۰۰', note='کروکی ملک')
        permit = self.reload()
        self.assertEqual((permit.sketch_state, permit.sketch['fee']), ('priced', 500_000))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='هزینه‌ی کروکی شمیم').exists())
        # the amount must match the fee; the slip needs a number and a date that is not in the future
        for bad in ({'amount': '400000'}, {'number': ''}, {'date': '1499/01/01'}, {'date': ''}):
            self.act(self.citizen, 'permit_sketch_pay', **{'amount': '500000', 'number': '12345', 'date': '1405/06/22', **bad})
            self.assertEqual(self.reload().sketch_state, 'priced', bad)
        client_for(self.citizen).post(self.url('permit_sketch_pay'), {'amount': '500000', 'number': '12345', 'date': '1405/06/22', 'slip': upload('slip.png', PNG)})
        permit = self.reload()
        self.assertEqual((permit.sketch_state, permit.sketch['payment']['number']), ('paid', '12345'))
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='sketch_slip').count(), 1)
        # delivery: needs the confirmation tick and a file; only the technical expert / dehyari
        sketch = upload('sketch.dxf', b'0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n')
        self.act(self.engineer, 'permit_sketch_deliver', sketch=sketch)                          # no tick
        self.assertEqual(self.reload().sketch_state, 'paid')
        self.act(self.clerk, 'permit_sketch_deliver', confirm='on', sketch=upload('s.dxf', b'0\nEOF\n'))
        self.assertEqual(self.reload().sketch_state, 'paid')
        self.act(self.dehyari, 'permit_sketch_deliver', confirm='on', sketch=upload('s2.dxf', b'0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n'))
        permit = self.reload()
        self.assertEqual(permit.sketch_state, 'delivered')
        self.assertEqual(permit.documents.filter(kind='shamim').count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='کروکی شمیم تحویل شد').exists())
        # now step 1 can be confirmed (with the defence form)
        sign_defence(self.citizen, permit)
        self.open_as(self.clerk, permit)
        self.assertEqual(self.reload(permit).stage_no, 2)

    def test_the_owner_with_a_shamim_file_cannot_ask_and_nobody_else_can_ask_for_him(self):
        owner_has_file = self.file_it()
        client_for(self.citizen).post(self.url('permit_sketch_request', owner_has_file))
        self.assertEqual(self.reload(owner_has_file).sketch_state, '')
        later = self.file_it(no_shamim=False)
        self.assertEqual(later.sketch_state, '')

    def test_the_owner_may_ask_later_in_step_one_when_he_did_not_at_filing(self):
        data = unlicensed()
        data.pop('shamim')
        data['shamim_request'] = ''
        self.assertEqual(client_for(self.citizen).post(reverse('main:without_permit_form'), data).status_code, 400)

    def test_the_sketch_page_is_for_the_owner_and_staff_and_the_fee_can_be_changed_until_paid(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_sketch')).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url('permit_sketch')).status_code, 404, who.profile.role)
        self.act(self.engineer, 'permit_sketch_fee', fee='500000')
        self.act(self.dehyari, 'permit_sketch_fee', fee='300000')
        self.assertEqual(self.reload().sketch['fee'], 300_000)
        for bad in ('0', '-5', 'abc', ''):
            self.act(self.engineer, 'permit_sketch_fee', fee=bad)
            self.assertEqual(self.reload().sketch['fee'], 300_000, bad)

    def test_a_permit_track_file_has_no_sketch_page(self):
        permit = Village.filed(self)
        self.assertEqual(client_for(self.citizen).get(self.url('permit_sketch', permit)).status_code, 404)
