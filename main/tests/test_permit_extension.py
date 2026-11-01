"""Building permit renewal: the one-year term, the request, the renewal form and the second term."""
import jdatetime

from main.models import Notification
from main.office import permit_extension
from main.tests.helpers import client_for, requires_gis_data
from main.tests.test_permit_step6 import AtStepSeven


def days_ago(days):
    return (jdatetime.date.today() - jdatetime.timedelta(days=days)).strftime('%Y/%m/%d')


class Issued(AtStepSeven):
    """A permit issued today."""

    def setUp(self):
        super().setUp()
        client_for(self.clerk).post(self.url('licence_issue'), {**self.form(permit_no='18/1286', issue_date=jdatetime.date.today().strftime('%Y/%m/%d')), 'signed': 'on'})
        self.reload()
        self.assertEqual(self.permit.licence_state, 'issued')

    def age(self, days):
        """Pretend the permit was issued ``days`` ago."""
        licence = dict(self.permit.licence)
        licence['f'] = {**licence['f'], 'issue_date': days_ago(days)}
        self.permit.licence = licence
        self.permit.save()

    def ask(self, who=None):
        return client_for(who or self.citizen).post(self.url('extension_request'))

    def answer(self, who=None, **change):
        defaults = permit_extension.defaults(self.reload(), permit_extension.open_extension(self.permit) or {})
        data = {**{f'q_{k}': v for k, v in defaults['req'].items()}, **{f'e_{k}': v for k, v in defaults['form'].items()}}
        data.update(change)
        return data

    def issue(self, who=None, **change):
        return client_for(who or self.clerk).post(self.url('extension_issue'), {'req_signed': 'on', 'signed': 'on', **self.answer(**change)})


@requires_gis_data
class TheTerm(Issued):
    def test_a_year_from_the_issue_date(self):
        info = permit_extension.expiry(self.permit)
        today = jdatetime.date.today()
        self.assertEqual(info['date'], f'{today.year + 1:04d}/{today.month:02d}/{today.day:02d}')
        self.assertEqual((info['state'], info['renewals']), ('valid', 0))
        self.assertEqual(self.permit.status_text, 'پروانه صادر و تحویل شد')

    def test_the_states_follow_the_calendar(self):
        self.age(340)
        self.assertEqual(permit_extension.expiry(self.reload())['state'], 'soon')
        self.assertIn('روز تا پایان مهلت', self.permit.status_text)
        self.age(400)
        self.assertEqual(permit_extension.expiry(self.reload())['state'], 'expired')
        self.assertEqual(self.permit.status_text, 'مهلت پروانه تمام شده؛ تمدید لازم است')

    def test_no_term_before_the_permit_is_issued(self):
        self.permit.licence_state = ''
        self.assertIsNone(permit_extension.expiry(self.permit))


@requires_gis_data
class Asking(Issued):
    def test_not_while_the_permit_is_valid(self):
        self.ask()
        self.assertFalse(self.reload().extensions)

    def test_the_owner_asks_once_it_has_expired_and_the_staff_are_told(self):
        self.age(400)
        self.ask()
        permit = self.reload()
        self.assertEqual([(e['term'], e['state']) for e in permit.extensions], [(1, 'requested')])
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='درخواست تمدید پروانه').exists())
        self.assertEqual(permit.status_text, 'درخواست تمدید پروانه منتظر دهیاری')
        self.assertTrue(permit.needs_staff)
        self.ask()
        self.assertEqual(len(self.reload().extensions), 1)

    def test_the_staff_may_ask_for_a_walk_in_owner_but_not_strangers(self):
        self.age(400)
        for who in (self.neighbour, self.stranger):
            self.ask(who)
        self.assertFalse(self.reload().extensions)
        self.ask(self.clerk)
        self.assertEqual(len(self.reload().extensions), 1)


@requires_gis_data
class Renewing(Issued):
    def setUp(self):
        super().setUp()
        self.age(400)
        self.ask()

    def test_the_form_is_filled_from_the_permit(self):
        data = permit_extension.defaults(self.reload(), permit_extension.open_extension(self.permit))
        self.assertEqual(data['req']['name'], 'علی رضایی')
        self.assertEqual((data['form']['fee_slip_no'], data['form']['ins_slip_no']), ('005952', '5850040418126010'))
        self.assertEqual(data['form']['period'], 'یک سال')
        self.assertEqual(data['form']['from_date'], permit_extension.expiry(self.permit)['date'])

    def test_the_staff_save_and_only_they(self):
        client_for(self.clerk).post(self.url('extension_save'), self.answer(e_section='مرکزی'))
        self.assertEqual(self.reload().extensions[0]['form']['section'], 'مرکزی')
        client_for(self.citizen).post(self.url('extension_save'), self.answer(e_section='x'))
        self.assertEqual(self.reload().extensions[0]['form']['section'], 'مرکزی')

    def test_issuing_needs_both_ticks_a_number_and_dates(self):
        for change in (dict(e_number=''), dict(e_date='bad'), dict(e_from_date='')):
            self.issue(**change)
            self.assertEqual(self.reload().extensions[0]['state'], 'requested', change)
        client_for(self.clerk).post(self.url('extension_issue'), {'signed': 'on', **self.answer()})
        client_for(self.clerk).post(self.url('extension_issue'), {'req_signed': 'on', **self.answer()})
        client_for(self.citizen).post(self.url('extension_issue'), {'req_signed': 'on', 'signed': 'on', **self.answer()})
        self.assertEqual(self.reload().extensions[0]['state'], 'requested')

    def test_the_renewal_starts_at_the_end_of_the_term_and_runs_a_year(self):
        before = permit_extension.expiry(self.reload())['date']
        self.issue(e_number='19/1617')
        permit = self.reload()
        self.assertEqual(permit.extensions[0]['state'], 'issued')
        info = permit_extension.expiry(permit)
        self.assertEqual(info['renewals'], 1)
        self.assertEqual(info['date'][5:], before[5:])
        self.assertEqual(int(info['date'][:4]), int(before[:4]) + 1)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='پروانه‌ی شما تمدید شد').exists())

    def test_at_most_two_renewals(self):
        self.issue()
        permit = self.reload()
        permit.extensions[0]['form']['from_date'] = days_ago(400)         # the first renewal began long ago too
        permit.save()
        self.ask()
        self.issue(e_number='19/1700')
        self.assertEqual(permit_extension.expiry(self.reload())['renewals'], 2)
        permit = self.reload()
        permit.extensions[1]['form']['from_date'] = days_ago(400)
        permit.save()
        self.ask()
        self.assertEqual(len(self.reload().extensions), 2)

    def test_the_pages(self):
        staff = client_for(self.clerk).get(self.url('extension')).content.decode()
        self.assertIn('name="e_number"', staff)
        self.assertIn('اثر انگشت متقاضی', staff)
        owner = client_for(self.citizen).get(self.url('extension')).content.decode()
        self.assertIn('امضا و تحویل دستی', owner)
        self.assertNotIn('ثبت تمدید', owner)
        self.assertEqual(client_for(self.neighbour).get(self.url('extension')).status_code, 404)


@requires_gis_data
class Notices(Issued):
    def test_owners_are_told_once_per_term(self):
        self.assertEqual(permit_extension.notify_expiring(), 0)
        self.age(340)
        self.assertEqual(permit_extension.notify_expiring(), 1)
        self.assertEqual(permit_extension.notify_expiring(), 0)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='مهلت پروانه‌ی ساختمان').exists())
        self.age(400)
        self.assertEqual(permit_extension.notify_expiring(), 1)
