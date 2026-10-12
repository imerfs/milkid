"""Payroll: employee register, monthly calculation, debts, daily workers, Eidi, tenant isolation."""
from datetime import date
from decimal import Decimal

from main.accounting import payroll
from main.models import PayrollSlip
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.tests.helpers import make_municipality
from main.tests.test_accounting_ledger import LedgerBase, make_user



def _nid(body):
    check = sum(int(d) * (10 - i) for i, d in enumerate(body)) % 11
    return body + str(check if check < 2 else 11 - check)


NID = [_nid('049937089'), _nid('068415941'), _nid('006774982'), _nid('123456789')]


class PayrollBase(LedgerBase):
    def emp(self, nid=NID[0], **kw):
        data = dict(first_name='علی', last_name='رضایی', national_id=nid, calc_group='official_worker',
                    list_title='کارگران رسمی', job_title='کارگر', start_date=date(2024, 1, 1))
        data.update(kw)
        e = payroll.add_employee(self.dehyar, **data)
        payroll.set_allowances(self.dehyar, e, {1: 30_000_000, 2: 3_000_000})   # 33m
        return e

    def other_actor(self):
        other = make_user('dehyari')
        make_municipality(other, village='دیگر')
        return other


class EmployeeTests(PayrollBase):
    def test_numbers_codes_and_national_id(self):
        a, b = self.emp(), self.emp(NID[1])
        self.assertEqual((a.code, b.code), (1, 2))
        with self.assertRaises(Conflict):
            self.emp(NID[0])
        for bad in ('123', '1234567890', '0000000000', 'abcdefghij'):
            with self.assertRaises(Invalid):
                self.emp(bad)

    def test_end_before_start_and_bad_group(self):
        with self.assertRaises(Invalid):
            self.emp(end_date=date(2023, 1, 1))
        with self.assertRaises(Invalid):
            self.emp(calc_group='x')

    def test_isolation_and_access(self):
        e = self.emp()
        other = self.other_actor()
        with self.assertRaises(NotFound):
            payroll.get_employee(other, e.pk)
        with self.assertRaises(NotFound):
            payroll.set_allowances(other, e, {1: 5})
        self.assertEqual(payroll.employees(other).count(), 0)
        with self.assertRaises(Forbidden):
            payroll.employees(make_user('citizen'))

    def test_cannot_delete_with_slips(self):
        e = self.emp()
        payroll.run_payroll(self.dehyar, 1404, 3)
        with self.assertRaises(Conflict):
            payroll.delete_employee(self.dehyar, e)


class CalculationTests(PayrollBase):
    def slip(self, e, year=1404, month=3):
        run = payroll.run_payroll(self.dehyar, year, month)
        return run.slips.get(employee=e)

    def test_plain_month(self):
        e = self.emp()
        s = self.slip(e)
        self.assertEqual(s.allowances, 33_000_000)
        self.assertEqual(s.insurable, 33_000_000)
        self.assertEqual(s.insurance_employee, 2_310_000)       # 7%
        self.assertEqual(s.insurance_org, 7_590_000)            # 20% + 3%
        self.assertEqual(s.net, 33_000_000 - 2_310_000)

    def test_absence_prorates_allowances(self):
        e = self.emp()
        payroll.set_attendance(self.dehyar, e, 1404, 3, absent_days=3)
        self.assertEqual(self.slip(e).allowances, 29_700_000)   # 27/30

    def test_overtime_uses_base_rate_and_personal_override(self):
        e = self.emp()
        payroll.set_attendance(self.dehyar, e, 1404, 3, ot_normal=10)
        hourly = Decimal(30_000_000) / 30 / Decimal('7.33') * Decimal('1.4')
        self.assertEqual(self.slip(e).overtime, int(hourly * 10 + Decimal('0.5')))
        payroll.set_personal_calc(self.dehyar, e, overtime_rate=100_000)
        self.assertEqual(self.slip(e).overtime, 1_000_000)

    def test_mission_and_misc_are_not_insurable(self):
        e = self.emp()
        payroll.set_personal_calc(self.dehyar, e, mission_day_rate=1_000_000)
        payroll.add_mission(self.dehyar, e, order_no='1', order_date=date(2025, 5, 20), start_date=date(2025, 5, 21),
                            end_date=date(2025, 5, 23), origin='الف', destination='ب', misc_cost=200_000)
        payroll.set_misc(self.dehyar, e, 1404, 3, transfer_amount=500_000, advance=100_000)
        s = self.slip(e)       # 1404/03/01 = 2025-05-22 area: mission starts 2025-05-21 = 1404/02/31
        self.assertEqual(s.mission, 0)
        s = self.slip(e, month=2)
        self.assertEqual(s.mission, 3_200_000)
        run = payroll.run_payroll(self.dehyar, 1404, 3)
        s = run.slips.get(employee=e)
        self.assertEqual(s.misc_transfer, 500_000)
        self.assertEqual(s.advance, 100_000)
        self.assertEqual(s.insurable, 33_000_000)
        self.assertEqual(s.net, 33_000_000 + 500_000 - 2_310_000 - 100_000)

    def test_no_insurance_type(self):
        e = self.emp(insurance_type='none')
        s = self.slip(e)
        self.assertEqual((s.insurable, s.insurance_employee, s.insurance_org), (0, 0, 0))

    def test_ceiling_and_minimum_wage(self):
        e = self.emp()
        payroll.update_settings(self.dehyar, insurance_ceiling=20_000_000)
        self.assertEqual(self.slip(e).insurable, 20_000_000)
        payroll.update_settings(self.dehyar, insurance_ceiling=0, min_daily_wage=2_000_000)
        self.assertEqual(self.slip(e).insurable, 60_000_000)

    def test_special_allowance_and_debt_by_group(self):
        e = self.emp()
        other = self.emp(NID[1], calc_group='retired')
        payroll.add_special_allowance(self.dehyar, 'official_worker', 'عیدی ماهانه', 1_000_000)
        payroll.add_special_debt(self.dehyar, 'official_worker', 'صندوق', 500_000, start_year=1404, start_month=3, months=2)
        run = payroll.run_payroll(self.dehyar, 1404, 3)
        s, o = run.slips.get(employee=e), run.slips.get(employee=other)
        self.assertEqual(s.special_allowances, 1_000_000)
        self.assertEqual(s.debts, 500_000)
        self.assertEqual(o.special_allowances, 0)
        self.assertEqual(payroll.run_payroll(self.dehyar, 1404, 5).slips.get(employee=e).debts, 0)   # ended after 2 months

    def test_negative_net_is_refused(self):
        e = self.emp()
        payroll.set_misc(self.dehyar, e, 1404, 3, advance=50_000_000)
        with self.assertRaises(Invalid):
            payroll.run_payroll(self.dehyar, 1404, 3)
        self.assertFalse(PayrollSlip.objects.exists())

    def test_employee_outside_service_is_skipped(self):
        self.emp(start_date=date(2030, 1, 1))
        with self.assertRaises(Invalid):
            payroll.run_payroll(self.dehyar, 1404, 3)

    def test_recompute_replaces_the_draft(self):
        e = self.emp()
        first = payroll.run_payroll(self.dehyar, 1404, 3)
        payroll.set_attendance(self.dehyar, e, 1404, 3, absent_days=30)
        second = payroll.run_payroll(self.dehyar, 1404, 3)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.slips.count(), 1)
        self.assertEqual(second.slips.get().allowances, 0)


class DebtAndFinalizeTests(PayrollBase):
    def test_debt_is_deducted_and_paid_off_on_finalize(self):
        e = self.emp()
        d = payroll.add_debt(self.dehyar, e, title='وام', total=3_000_000, installment=2_000_000, start_year=1404, start_month=3)
        r3 = payroll.run_payroll(self.dehyar, 1404, 3)
        self.assertEqual(r3.slips.get().debts, 2_000_000)
        payroll.finalize_run(self.dehyar, r3)
        d.refresh_from_db()
        self.assertEqual(d.paid, 2_000_000)
        r4 = payroll.run_payroll(self.dehyar, 1404, 4)
        self.assertEqual(r4.slips.get().debts, 1_000_000)       # the remainder only
        payroll.finalize_run(self.dehyar, r4)
        d.refresh_from_db()
        self.assertEqual(d.remaining, 0)
        self.assertEqual(payroll.run_payroll(self.dehyar, 1404, 5).slips.get().debts, 0)

    def test_final_run_is_frozen_and_ordered(self):
        e = self.emp()
        r3 = payroll.run_payroll(self.dehyar, 1404, 3)
        r4 = payroll.run_payroll(self.dehyar, 1404, 4)
        with self.assertRaises(Conflict):
            payroll.finalize_run(self.dehyar, r4)               # month 3 still draft
        payroll.finalize_run(self.dehyar, r3)
        for call in (lambda: payroll.finalize_run(self.dehyar, r3), lambda: payroll.run_payroll(self.dehyar, 1404, 3),
                     lambda: payroll.delete_run(self.dehyar, r3),
                     lambda: payroll.set_attendance(self.dehyar, e, 1404, 3, worked_days=20),
                     lambda: payroll.set_misc(self.dehyar, e, 1404, 3, advance=1)):
            with self.subTest(call=call), self.assertRaises(Conflict):
                call()

    def test_debt_validation(self):
        e = self.emp()
        for kw in (dict(total=0, installment=1), dict(total=10, installment=20), dict(total=10, installment=5, start_month=13)):
            data = dict(title='x', total=10, installment=5, start_year=1404, start_month=1)
            data.update(kw)
            with self.assertRaises(Invalid):
                payroll.add_debt(self.dehyar, e, **data)

    def test_run_isolation(self):
        self.emp()
        run = payroll.run_payroll(self.dehyar, 1404, 3)
        other = self.other_actor()
        with self.assertRaises(NotFound):
            payroll.finalize_run(other, run)
        with self.assertRaises(NotFound):
            payroll.get_run(other, run.pk)


class AttendanceValidationTests(PayrollBase):
    def test_bounds(self):
        e = self.emp()
        for kw in (dict(absent_days=31), dict(ot_normal=-1), dict(bonus_pct=101), dict(worked_days='x')):
            with self.assertRaises(Invalid):
                payroll.set_attendance(self.dehyar, e, 1404, 3, **kw)
        with self.assertRaises(Invalid):
            payroll.set_attendance(self.dehyar, e, 1404, 13)

    def test_mission_dates(self):
        e = self.emp()
        with self.assertRaises(Invalid):
            payroll.add_mission(self.dehyar, e, order_no='1', order_date=date(2025, 5, 1), start_date=date(2025, 5, 5),
                                end_date=date(2025, 5, 1), origin='الف', destination='ب')


class DailyWorkerTests(PayrollBase):
    def test_month_figures(self):
        w = payroll.add_worker(self.dehyar, first_name='رضا', last_name='احمدی', national_id=NID[2])
        m = payroll.record_worker_month(self.dehyar, w, 1404, 3, daily_wage=1_000_000, days=20, housing=300_000,
                                        grocery=200_000, advance=100_000, insurance_employee=1_400_000, tax_pct=10)
        self.assertEqual(m.gross, 20_500_000)
        self.assertEqual(m.tax, 2_050_000)
        self.assertEqual(m.net, 20_500_000 - 1_400_000 - 100_000 - 2_050_000)

    def test_rules(self):
        w = payroll.add_worker(self.dehyar, first_name='رضا', last_name='احمدی', national_id=NID[2])
        with self.assertRaises(Conflict):
            payroll.add_worker(self.dehyar, first_name='x', last_name='y', national_id=NID[2])
        with self.assertRaises(Invalid):
            payroll.record_worker_month(self.dehyar, w, 1404, 3, daily_wage=0, days=5)
        with self.assertRaises(NotFound):
            payroll.record_worker_month(self.other_actor(), w, 1404, 3, daily_wage=1, days=5)


class EidiTests(PayrollBase):
    def test_amount_cap_and_advance(self):
        e = self.emp()
        payroll.set_eidi_setting(self.dehyar, 1404, 'official_worker', fixed_amount=36_000_000, cap=0, annual_days=360)
        self.assertEqual(payroll.compute_eidi(self.dehyar, 1404), 1)
        self.assertEqual(payroll.eidi_records(self.dehyar, 1404).get().amount, 36_000_000)
        payroll.set_eidi_setting(self.dehyar, 1404, 'official_worker', fixed_amount=36_000_000, cap=30_000_000,
                                 advance=5_000_000)
        payroll.compute_eidi(self.dehyar, 1404, {e.id: (180, 0, 0)})
        self.assertEqual(payroll.eidi_records(self.dehyar, 1404).get().amount, 13_000_000)   # half year, no cap hit, - advance

    def test_needs_setting_and_valid_days(self):
        e = self.emp()
        with self.assertRaises(Invalid):
            payroll.compute_eidi(self.dehyar, 1404)
        payroll.set_eidi_setting(self.dehyar, 1404, 'official_worker', fixed_amount=1_000_000)
        with self.assertRaises(Invalid):
            payroll.compute_eidi(self.dehyar, 1404, {e.id: (400, 0, 0)})


class SettingsTests(PayrollBase):
    def test_validation_and_titles(self):
        with self.assertRaises(Invalid):
            payroll.update_settings(self.dehyar, insurance_employee_pct=90)
        with self.assertRaises(Invalid):
            payroll.update_settings(self.dehyar, bogus=1)
        payroll.set_title(self.dehyar, 3, 'حق تاهل')
        self.assertEqual(payroll.titles_of(self.dehyar)[3], 'حق تاهل')
        self.assertEqual(len(payroll.titles_of(self.dehyar)), 40)
        with self.assertRaises(Invalid):
            payroll.set_title(self.dehyar, 41, 'x')
