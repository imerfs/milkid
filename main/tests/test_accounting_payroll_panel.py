"""Workspace pages of payroll (HTTP level): forms, validation, period actions, tenant isolation."""
from main.accounting import payroll
from main.models import Employee, PayrollRun
from main.tests.helpers import client_for, make_municipality
from main.tests.test_accounting_finance_panel import FinancePanelBase
from main.tests.test_accounting_panel import make_user
from main.tests.test_accounting_payroll import NID

EMP = {'first_name': 'علی', 'last_name': 'رضایی', 'national_id': NID[0], 'gender': 'm', 'marital': 'single',
       'calc_group': 'official_worker', 'list_title': 'کارگران رسمی', 'job_title': 'کارگر', 'start_date': '۱۴۰۳/۰۱/۰۱',
       'insurance_type': 'social', 'ins_main': '1'}


class PayrollPanelBase(FinancePanelBase):
    def make_emp(self, nid=NID[0], **extra):
        r = self.post('acc_p_emp_new', **{**EMP, 'national_id': nid, **extra})
        self.assertEqual(r.status_code, 204, r.content.decode()[:600])
        emp = Employee.objects.get(national_id=nid)
        r = self.post('acc_p_emp_allowances', emp.id, a1='۳۰٬۰۰۰٬۰۰۰', a2='۳٬۰۰۰٬۰۰۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:600])
        return emp


class TabTests(PayrollPanelBase):
    def test_all_tabs_render(self):
        for tab in ('pstaff', 'pcalc', 'pattendance', 'pmission', 'pspecialallow', 'pspecialdebt', 'pmisc', 'pworkers',
                    'peidi', 'prun', 'psettings'):
            r = self.get('acc_panel', tab=tab)
            self.assertEqual(r.status_code, 200, tab)

    def test_forms_open(self):
        emp = self.make_emp()
        for name, args in (('acc_p_emp_new', ()), ('acc_p_emp_edit', (emp.id,)), ('acc_p_emp_allowances', (emp.id,)),
                           ('acc_p_emp_calc', (emp.id,)), ('acc_p_emp_debts', (emp.id,)), ('acc_p_debt_new', (emp.id,)),
                           ('acc_p_attendance', (1404, 3, emp.id)), ('acc_p_misc', (1404, 3, emp.id)),
                           ('acc_p_mission_new', ()), ('acc_p_special_new', ('allowance',)), ('acc_p_special_new', ('debt',)),
                           ('acc_p_worker_new', ()), ('acc_p_eidi_setting', (1404,)), ('acc_p_paysettings', ()),
                           ('acc_p_paytitles', ())):
            self.assertEqual(self.get(name, *args).status_code, 200, name)

    def test_citizen_refused(self):
        r = client_for(make_user('citizen')).post('/accounting/panel/payroll/employee/new/')
        self.assertIn(r.status_code, (302, 403, 404))


class EmployeeFlowTests(PayrollPanelBase):
    def test_create_edit_delete(self):
        emp = self.make_emp()
        self.assertContains(self.get('acc_panel', tab='pstaff'), 'رضایی')
        r = self.post('acc_p_emp_edit', emp.id, **{**EMP, 'last_name': 'محمدی'})
        self.assertEqual(r.status_code, 204)
        emp.refresh_from_db()
        self.assertEqual(emp.last_name, 'محمدی')
        self.assertEqual(self.post('acc_p_emp_delete', emp.id).status_code, 204)
        self.assertFalse(Employee.objects.exists())

    def test_bad_national_id_and_duplicate(self):
        r = self.post('acc_p_emp_new', **{**EMP, 'national_id': '1234567890'})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Employee.objects.exists())
        self.make_emp()
        self.assertEqual(self.post('acc_p_emp_new', **EMP).status_code, 409)

    def test_other_municipality_cannot_touch(self):
        emp = self.make_emp()
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        c = client_for(other)
        for name in ('acc_p_emp_edit', 'acc_p_emp_allowances', 'acc_p_emp_debts', 'acc_p_emp_calc'):
            from django.urls import reverse
            self.assertEqual(c.get(reverse(f'main:{name}', args=[emp.id])).status_code, 404, name)
        self.assertEqual(c.post(reverse('main:acc_p_emp_delete', args=[emp.id])).status_code, 404)


class DebtAndRunFlowTests(PayrollPanelBase):
    def test_debt_then_run_then_finalize(self):
        emp = self.make_emp()
        r = self.post('acc_p_debt_new', emp.id, title='وام', total='۳٬۰۰۰٬۰۰۰', installment='۱٬۰۰۰٬۰۰۰', start_year='1404',
                      start_month='3')
        self.assertEqual(r.status_code, 204, r.content.decode()[:500])
        self.assertContains(self.get('acc_p_emp_debts', emp.id), 'وام')
        r = self.post('acc_p_run', 1404, 3)
        self.assertEqual(r.status_code, 204)
        run = PayrollRun.objects.get()
        self.assertEqual(run.slips.get().debts, 1_000_000)
        self.assertContains(self.get('acc_panel', tab='prun', py=1404, pm=3), 'رضایی')
        self.assertContains(self.get('acc_p_slip', run.slips.get().id), 'خالص پرداختی')
        x = self.get('acc_p_run_export', run.id)
        self.assertEqual(x.status_code, 200)
        self.assertIn('spreadsheetml', x['Content-Type'])
        self.assertEqual(self.post('acc_p_run_finalize', run.id).status_code, 204)
        self.assertEqual(self.post('acc_p_run_delete', run.id).status_code, 409)
        self.assertEqual(payroll.runs_for(self.dehyar).get().status, 'final')

    def test_negative_net_is_a_visible_error(self):
        emp = self.make_emp()
        self.post('acc_p_misc', 1404, 3, emp.id, transfer_amount='', advance='۹۹٬۰۰۰٬۰۰۰')
        r = self.post('acc_p_run', 1404, 3)
        self.assertIn(r.status_code, (400, 409))
        self.assertFalse(PayrollRun.objects.exists())


class MonthlyInputTests(PayrollPanelBase):
    def test_attendance_validation_and_save(self):
        emp = self.make_emp()
        self.assertEqual(self.post('acc_p_attendance', 1404, 3, emp.id, absent_days='۳۱').status_code, 400)
        r = self.post('acc_p_attendance', 1404, 3, emp.id, absent_days='۲', ot_normal='۵')
        self.assertEqual(r.status_code, 204)
        self.assertContains(self.get('acc_panel', tab='pattendance', py=1404, pm=3), 'رضایی')

    def test_special_and_mission(self):
        emp = self.make_emp()
        r = self.post('acc_p_special_new', 'allowance', calc_group='official_worker', title='مزایا', amount='۱٬۰۰۰٬۰۰۰')
        self.assertEqual(r.status_code, 204)
        r = self.post('acc_p_special_new', 'debt', calc_group='official_worker', title='صندوق', installment='۱۰۰', start_year='1404',
                      start_month='3', months='۶')
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.post('acc_p_special_new', 'bogus').status_code, 404)
        r = self.post('acc_p_mission_new', employee=emp.id, order_no='۱', order_date='۱۴۰۴/۰۲/۱۰', start_date='۱۴۰۴/۰۲/۱۱',
                      end_date='۱۴۰۴/۰۲/۱۳', origin='الف', destination='ب')
        self.assertEqual(r.status_code, 204, r.content.decode()[:500])
        r = self.post('acc_p_mission_new', employee=emp.id, order_no='۲', order_date='۱۴۰۴/۰۲/۱۰', start_date='۱۴۰۴/۰۲/۱۳',
                      end_date='۱۴۰۴/۰۲/۱۱', origin='الف', destination='ب')
        self.assertEqual(r.status_code, 400)

    def test_worker_and_eidi(self):
        emp = self.make_emp()
        r = self.post('acc_p_worker_new', first_name='رضا', last_name='احمدی', national_id=NID[2], gender='m')
        self.assertEqual(r.status_code, 204, r.content.decode()[:500])
        worker = payroll.workers(self.dehyar).get()
        r = self.post('acc_p_worker_month', 1404, 3, worker.id, daily_wage='۱٬۰۰۰٬۰۰۰', days='۲۰')
        self.assertEqual(r.status_code, 204, r.content.decode()[:500])
        self.assertEqual(self.post('acc_p_worker_month', 1404, 3, worker.id, daily_wage='۰', days='۲۰').status_code, 400)
        self.assertEqual(self.post('acc_p_eidi_compute', 1404).status_code, 400)       # no setting yet
        r = self.post('acc_p_eidi_setting', 1404, calc_group='official_worker', fixed_amount='۳۶٬۰۰۰٬۰۰۰', annual_days='360')
        self.assertEqual(r.status_code, 204, r.content.decode()[:500])
        self.assertEqual(self.post('acc_p_eidi_compute', 1404).status_code, 204)
        self.assertEqual(self.post('acc_p_eidi_days', 1404, emp.id, worked='۱۸۰', absent='۰', sick='۰').status_code, 204)
        self.assertEqual(payroll.eidi_records(self.dehyar, 1404).get().amount, 18_000_000)

    def test_settings(self):
        self.assertEqual(self.post('acc_p_paysettings', **{'month_days': '30', 'hours_per_day': '7.33', 'overtime_multiplier': '1.4',
                                                          'holiday_multiplier': '1.4', 'night_pct': '35', 'insurance_employee_pct': '90',
                                                          'insurance_employer_pct': '20', 'unemployment_pct': '3'}).status_code, 400)
        r = self.post('acc_p_paysettings', **{'month_days': '30', 'hours_per_day': '7.33', 'overtime_multiplier': '1.5',
                                             'holiday_multiplier': '1.4', 'night_pct': '35', 'insurance_employee_pct': '7',
                                             'insurance_employer_pct': '20', 'unemployment_pct': '3'})
        self.assertEqual(r.status_code, 204, r.content.decode()[:500])
        self.assertEqual(payroll.settings_of(self.dehyar).overtime_multiplier, 1.5)
