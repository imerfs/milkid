"""Payroll (حقوق و دستمزد): staff register, monthly inputs, the monthly calculation, daily workers and the Eidi bonus.

Money is whole rials, rounded half-up. The legal rates (insurance %, overtime multiplier...) are stored per municipality
in PayrollSettings; salary tax is NOT computed here: the amount from the tax system is entered per employee
(PersonalCalc.tax_amount), as in the software this replaces.

Calculation of one slip (see `calculate`):
  factor      = (worked days - absent days) / month days, allowances are prorated by it
  base        = allowance slot 1 (the basic wage); hourly rates derive from it unless the personal rate is set
  gross       = allowances + special allowances + overtime + night + holiday work + bonus + mission + misc transfer
  insurable   = gross without mission and misc transfer (capped by the ceiling, lifted to the minimum wage)
  deductions  = employee insurance + medical + supplementary + life insurance + housing + debts + welfare + advance + tax
  net         = gross - deductions (a negative net is refused: fix the inputs)
"""
from decimal import ROUND_HALF_UP, Decimal

import jdatetime
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import (AllowanceTitle, DailyWorker, DailyWorkerMonth, EidiRecord, EidiSetting, Employee,
                         EmployeeAllowance, EmployeeDebt, MiscPayment, Mission, MonthlyAttendance, Municipality,
                         PayrollRun, PayrollSettings, PayrollSlip, PersonalCalc, SpecialAllowance, SpecialDebt)
from main.models_payroll import CALC_GROUPS
from main.office.errors import Conflict, Invalid

SLOTS = range(1, 41)
DEFAULT_TITLES = ['حقوق و دستمزد روزانه', 'حق مسکن', 'حق خواربار', 'حق اولاد', 'سنوات', 'فوق‌العاده شغل',
                  'فوق‌العاده مدیریت', 'فوق‌العاده بدی آب و هوا', 'فوق‌العاده سختی کار', 'فوق‌العاده ایثارگری',
                  'فوق‌العاده تحصیلی', 'فوق‌العاده جذب']
GROUPS = dict(CALC_GROUPS)
INT_FIELDS = ('children', 'ins_main', 'ins_dep1', 'ins_dep2', 'ins_dep3', 'supp_normal', 'supp_special1',
              'supp_special2', 'supp_special3')


def _round(value):
    return Decimal(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _num(value, label, *, maximum=10_000):
    """A non-negative quantity (hours, days, percent)."""
    try:
        number = Decimal(str(value if value not in (None, '') else 0).replace(',', '').strip())
    except Exception:
        raise Invalid(f'{label} نامعتبر است.')
    if not number.is_finite() or number < 0 or number > maximum:
        raise Invalid(f'{label} نامعتبر است.')
    return number


def _period(year, month):
    year, month = int(year), int(month)
    if not (1300 <= year <= 1500) or not (1 <= month <= 12):
        raise Invalid('سال یا ماه نامعتبر است.')
    return year, month


def _before_or_equal(y1, m1, y2, m2):
    return (y1, m1) <= (y2, m2)


def settings_of(actor):
    muni = municipality_of(actor)
    obj, created = PayrollSettings.objects.get_or_create(municipality=muni)
    if created:
        obj.refresh_from_db()   # decimals as stored, not the float defaults of the new instance
    return obj


def update_settings(actor, **values):
    obj = settings_of(actor)
    spec = {'month_days': (1, 31), 'hours_per_day': (1, 24), 'overtime_multiplier': (1, 10), 'holiday_multiplier': (1, 10),
            'night_pct': (0, 200), 'insurance_employee_pct': (0, 50), 'insurance_employer_pct': (0, 50),
            'unemployment_pct': (0, 50)}
    with transaction.atomic():
        for name, value in values.items():
            if name in spec:
                number = _num(value, name)
                low, high = spec[name]
                if not (low <= number <= high):
                    raise Invalid('مقدار خارج از محدوده مجاز است.')
                setattr(obj, name, int(number) if name == 'month_days' else number)
            elif name in ('insurance_ceiling', 'min_daily_wage'):
                setattr(obj, name, _amount(value))
            else:
                raise Invalid('تنظیم نامعتبر است.')
        obj.save()
    return obj


# ---- allowance titles ---------------------------------------------------------------------------------------------

def titles_of(actor):
    """{slot: title} for slots 1..40, defaults filled in for unnamed ones."""
    muni = municipality_of(actor)
    saved = dict(AllowanceTitle.objects.filter(municipality=muni).values_list('slot', 'title'))
    return {s: saved.get(s) or (DEFAULT_TITLES[s - 1] if s <= len(DEFAULT_TITLES) else f'مزایای {s}') for s in SLOTS}


def set_title(actor, slot, title):
    muni = municipality_of(actor)
    if slot not in SLOTS:
        raise Invalid('شماره ردیف مزایا نامعتبر است.')
    title = _text(title, 'عنوان')[:100]
    AllowanceTitle.objects.update_or_create(municipality=muni, slot=slot, defaults={'title': title})


# ---- employees ----------------------------------------------------------------------------------------------------

def employees(actor, *, active=None):
    qs = Employee.objects.filter(municipality=municipality_of(actor))
    return qs if active is None else qs.filter(active=active)


def get_employee(actor, pk):
    return _own(municipality_of(actor), Employee.objects.filter(pk=pk).first())


def _check_national_id(value):
    value = (value or '').strip()
    if not (value.isdigit() and len(value) == 10):
        raise Invalid('شماره ملی باید ده رقم باشد.')
    if len(set(value)) == 1:
        raise Invalid('شماره ملی نامعتبر است.')
    check = sum(int(d) * (10 - i) for i, d in enumerate(value[:9])) % 11
    if int(value[9]) != (check if check < 2 else 11 - check):
        raise Invalid('شماره ملی نامعتبر است.')
    return value


def _employee_values(muni, v):
    v = dict(v)
    v['national_id'] = _check_national_id(v.get('national_id'))
    for name, label in (('first_name', 'نام'), ('last_name', 'نام خانوادگی'), ('job_title', 'عنوان شغل'),
                        ('list_title', 'عنوان لیست')):
        v[name] = _text(v.get(name), label)[:100]
    if v.get('calc_group') not in GROUPS:
        raise Invalid('گروه محاسباتی نامعتبر است.')
    for name in INT_FIELDS:
        if name in v:
            v[name] = int(_num(v[name], name, maximum=20))
    if v.get('start_date') is None:
        raise Invalid('تاریخ شروع خدمت را وارد کنید.')
    if v.get('end_date') and v['end_date'] < v['start_date']:
        raise Invalid('پایان خدمت نمی‌تواند قبل از شروع باشد.')
    if v.get('cost_center') is not None:
        _own_or_invalid(muni, v['cost_center'], 'مرکز هزینه')
    return v


def add_employee(actor, **values):
    muni = municipality_of(actor)
    values = _employee_values(muni, values)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if Employee.objects.filter(municipality=muni, national_id=values['national_id']).exists():
            raise Conflict('پرسنلی با این شماره ملی قبلاً ثبت شده است.')
        code = values.pop('code', None) or ((Employee.objects.filter(municipality=muni).order_by('-code').values_list(
            'code', flat=True).first() or 0) + 1)
        if Employee.objects.filter(municipality=muni, code=code).exists():
            raise Conflict('این شماره شناسایی قبلاً استفاده شده است.')
        emp = Employee.objects.create(municipality=muni, code=code, created_by=actor, **values)
        PersonalCalc.objects.create(employee=emp)
        return emp


def update_employee(actor, emp, **values):
    muni = municipality_of(actor)
    _own(muni, emp)
    values = _employee_values(muni, values)
    values.pop('code', None)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if Employee.objects.filter(municipality=muni, national_id=values['national_id']).exclude(pk=emp.pk).exists():
            raise Conflict('پرسنلی با این شماره ملی قبلاً ثبت شده است.')
        for name, value in values.items():
            setattr(emp, name, value)
        emp.save()
    return emp


def delete_employee(actor, emp):
    muni = municipality_of(actor)
    _own(muni, emp)
    with transaction.atomic():
        emp = _locked(Employee, emp.pk)
        if emp.slips.exists():
            raise Conflict('برای این فرد فیش حقوقی صادر شده و حذف نمی‌شود؛ آن را غیرفعال کنید.')
        emp.delete()


def calc_of(emp):
    obj, _ = PersonalCalc.objects.get_or_create(employee=emp)
    return obj


def set_allowances(actor, emp, amounts):
    """amounts: {slot: rials}. Slots left out (or zero) are removed."""
    muni = municipality_of(actor)
    _own(muni, emp)
    clean = {}
    for slot, value in amounts.items():
        if slot not in SLOTS:
            raise Invalid('ردیف مزایا نامعتبر است.')
        value = _amount(value)
        if value > 0:
            clean[slot] = value
    with transaction.atomic():
        emp.allowances.all().delete()
        EmployeeAllowance.objects.bulk_create([EmployeeAllowance(employee=emp, slot=s, amount=a) for s, a in clean.items()])


_CALC_MONEY = ('mission_day_rate', 'overtime_rate', 'holiday_overtime_rate', 'min_daily_wage', 'life_insurance_employee',
               'life_insurance_org', 'housing_installment', 'medical_main', 'medical_dep1', 'medical_dep2',
               'medical_dep3', 'supplementary_amount', 'tax_amount')


def set_personal_calc(actor, emp, **values):
    muni = municipality_of(actor)
    _own(muni, emp)
    calc = calc_of(emp)
    for name, value in values.items():
        if name in _CALC_MONEY:
            setattr(calc, name, _amount(value))
        elif name in ('insurance_employee_pct', 'insurance_employer_pct'):
            number = _num(value, 'درصد', maximum=100)
            setattr(calc, name, number)
        else:
            raise Invalid('فیلد نامعتبر است.')
    calc.save()
    return calc


# ---- debts --------------------------------------------------------------------------------------------------------

def add_debt(actor, emp, *, title, total, installment, org_share=0, start_year, start_month, note=''):
    muni = municipality_of(actor)
    _own(muni, emp)
    total, installment, org_share = _amount(total), _amount(installment), _amount(org_share)
    if total <= 0 or installment <= 0:
        raise Invalid('کل بدهی و قسط باید بیشتر از صفر باشد.')
    if installment > total:
        raise Invalid('قسط نمی‌تواند از کل بدهی بیشتر باشد.')
    y, m = _period(start_year, start_month)
    return EmployeeDebt.objects.create(employee=emp, title=_text(title, 'عنوان بدهی')[:100], total=total,
                                       installment=installment, org_share=org_share, start_year=y, start_month=m,
                                       note=_text(note, 'توضیحات', False)[:300])


def delete_debt(actor, debt):
    muni = municipality_of(actor)
    _own(muni, debt.employee)
    if debt.paid > 0:
        raise Conflict('از این بدهی قسط کسر شده و حذف نمی‌شود؛ آن را غیرفعال کنید.')
    debt.delete()


def set_debt_active(actor, debt, active):
    _own(municipality_of(actor), debt.employee)
    debt.active = bool(active)
    debt.save(update_fields=['active'])


# ---- monthly inputs -----------------------------------------------------------------------------------------------

def _run_final(muni, year, month):
    return PayrollRun.objects.filter(municipality=muni, year=year, month=month, status='final').exists()


def _guard_month(muni, year, month):
    if _run_final(muni, year, month):
        raise Conflict('حقوق این ماه قطعی شده و ورودی آن تغییر نمی‌کند.')


_ATT = ('ot_normal', 'ot_holiday', 'ot_incentive', 'holiday_work_days', 'night_hours', 'absent_days', 'sick_days',
        'worked_days', 'bonus_pct', 'welfare_pct')


def attendance_for(actor, year, month):
    muni = municipality_of(actor)
    year, month = _period(year, month)
    return MonthlyAttendance.objects.filter(employee__municipality=muni, year=year, month=month).select_related('employee')


def set_attendance(actor, emp, year, month, **values):
    muni = municipality_of(actor)
    _own(muni, emp)
    year, month = _period(year, month)
    clean = {}
    for name in _ATT:
        clean[name] = _num(values.get(name), name, maximum=100 if name.endswith('_pct') else 744)
    days = settings_of(actor).month_days
    if clean['worked_days'] > days or clean['absent_days'] > days or clean['sick_days'] > days:
        raise Invalid('روزهای کارکرد، غیبت و استعلاجی نمی‌تواند از روزهای ماه بیشتر باشد.')
    with transaction.atomic():
        _locked(Municipality, muni.id)
        _guard_month(muni, year, month)
        obj, _ = MonthlyAttendance.objects.update_or_create(employee=emp, year=year, month=month, defaults=clean)
    return obj


def delete_attendance(actor, row):
    muni = municipality_of(actor)
    _own(muni, row.employee)
    _guard_month(muni, row.year, row.month)
    row.delete()


def missions_for(actor):
    return Mission.objects.filter(employee__municipality=municipality_of(actor)).select_related('employee')


def add_mission(actor, emp, *, order_no, order_date, start_date, end_date, origin, destination, distance_km=0,
                driving_right=False, bad_weather=0, misc_cost=0):
    muni = municipality_of(actor)
    _own(muni, emp)
    if start_date is None or end_date is None or end_date < start_date:
        raise Invalid('تاریخ خاتمه نمی‌تواند قبل از تاریخ شروع باشد.')
    if (end_date - start_date).days > 366:
        raise Invalid('مدت ماموریت بیش از یک سال است.')
    if not (emp.start_date <= start_date) or (emp.end_date and start_date > emp.end_date):
        raise Invalid('ماموریت باید در دوره خدمت فرد باشد.')
    return Mission.objects.create(
        employee=emp, order_no=_text(order_no, 'شماره حکم')[:40], order_date=order_date, start_date=start_date,
        end_date=end_date, origin=_text(origin, 'شهر مبدا')[:80], destination=_text(destination, 'شهر مقصد')[:80],
        distance_km=int(_num(distance_km, 'فاصله', maximum=20000)), driving_right=bool(driving_right),
        bad_weather=_amount(bad_weather), misc_cost=_amount(misc_cost))


def delete_mission(actor, mission):
    muni = municipality_of(actor)
    _own(muni, mission.employee)
    y, m = _jalali_ym(mission.start_date)
    _guard_month(muni, y, m)
    mission.delete()


def _jalali_ym(d):
    j = jdatetime.date.fromgregorian(date=d)
    return j.year, j.month


def _special(model, actor, group, **values):
    muni = municipality_of(actor)
    if group not in GROUPS:
        raise Invalid('گروه محاسباتی نامعتبر است.')
    return model.objects.create(municipality=muni, calc_group=group, **values)


def special_allowances(actor):
    return SpecialAllowance.objects.filter(municipality=municipality_of(actor))


def add_special_allowance(actor, group, title, amount):
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ باید بیشتر از صفر باشد.')
    return _special(SpecialAllowance, actor, group, title=_text(title, 'عنوان مزایا')[:100], amount=amount)


def special_debts(actor):
    return SpecialDebt.objects.filter(municipality=municipality_of(actor))


def add_special_debt(actor, group, title, installment, *, start_year, start_month, months=12, org_share=0, note=''):
    installment = _amount(installment)
    if installment <= 0:
        raise Invalid('مبلغ قسط باید بیشتر از صفر باشد.')
    y, m = _period(start_year, start_month)
    months = int(_num(months, 'تعداد ماه', maximum=360))
    if months < 1:
        raise Invalid('تعداد ماه باید حداقل یک باشد.')
    return _special(SpecialDebt, actor, group, title=_text(title, 'عنوان بدهی')[:100], installment=installment,
                    org_share=_amount(org_share), start_year=y, start_month=m, months=months,
                    note=_text(note, 'توضیحات', False)[:300])


def delete_special(actor, obj):
    _own(municipality_of(actor), obj)
    obj.delete()


def misc_for(actor, year, month):
    year, month = _period(year, month)
    return MiscPayment.objects.filter(employee__municipality=municipality_of(actor), year=year,
                                      month=month).select_related('employee')


def set_misc(actor, emp, year, month, *, transfer_amount=0, advance=0):
    muni = municipality_of(actor)
    _own(muni, emp)
    year, month = _period(year, month)
    transfer_amount, advance = _amount(transfer_amount), _amount(advance)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        _guard_month(muni, year, month)
        if transfer_amount == 0 and advance == 0:
            MiscPayment.objects.filter(employee=emp, year=year, month=month).delete()
            return None
        obj, _ = MiscPayment.objects.update_or_create(employee=emp, year=year, month=month,
                                                      defaults={'transfer_amount': transfer_amount, 'advance': advance})
    return obj


# ---- the monthly calculation --------------------------------------------------------------------------------------

def debts_due(emp, year, month):
    """[(debt, amount)] taken from the employee this month: active personal debts that have started."""
    due = []
    for debt in emp.debts.filter(active=True):
        if _before_or_equal(debt.start_year, debt.start_month, year, month) and debt.remaining > 0:
            due.append((debt, min(debt.installment, debt.remaining)))
    return due


def _special_debt_total(emp, year, month):
    total = Decimal(0)
    for sd in SpecialDebt.objects.filter(municipality_id=emp.municipality_id, calc_group=emp.calc_group):
        index = (year - sd.start_year) * 12 + (month - sd.start_month)
        if 0 <= index < sd.months:
            total += sd.installment
    return total


def _in_service(emp, year, month):
    first = jdatetime.date(year, month, 1).togregorian()
    last = (jdatetime.date(year + (month == 12), month % 12 + 1, 1) - jdatetime.timedelta(days=1)).togregorian()
    return emp.active and emp.start_date <= last and (emp.end_date is None or emp.end_date >= first)


def calculate(emp, year, month, cfg):
    """Pure computation of one employee's slip fields (no writes)."""
    calc = calc_of(emp)
    days = Decimal(cfg.month_days)
    att = MonthlyAttendance.objects.filter(employee=emp, year=year, month=month).first()
    worked = (att.worked_days or days) if att else days
    absent = att.absent_days if att else Decimal(0)
    factor = max(worked - absent, Decimal(0)) / days
    amounts = dict(emp.allowances.values_list('slot', 'amount'))
    base = amounts.get(1, Decimal(0))
    allowances = _round(sum(amounts.values(), Decimal(0)) * factor)
    group_special = SpecialAllowance.objects.filter(municipality_id=emp.municipality_id, calc_group=emp.calc_group)
    special = group_special.aggregate(s=Sum('amount'))['s'] or Decimal(0)
    daily, hourly = base / days, base / days / cfg.hours_per_day
    ot_rate = calc.overtime_rate or hourly * cfg.overtime_multiplier
    holiday_rate = calc.holiday_overtime_rate or hourly * cfg.holiday_multiplier
    overtime = night = holiday_work = bonus = Decimal(0)
    welfare = Decimal(0)
    if att:
        overtime = _round((att.ot_normal + att.ot_incentive) * ot_rate + att.ot_holiday * holiday_rate)
        night = _round(att.night_hours * hourly * cfg.night_pct / 100)
        holiday_work = _round(att.holiday_work_days * daily * (cfg.holiday_multiplier - 1))
        bonus = _round(allowances * att.bonus_pct / 100)
        welfare = _round(allowances * att.welfare_pct / 100)
    mission = Decimal(0)
    for m in Mission.objects.filter(employee=emp):
        if _jalali_ym(m.start_date) == (year, month):
            mission += m.days * calc.mission_day_rate + m.bad_weather + m.misc_cost
    misc = MiscPayment.objects.filter(employee=emp, year=year, month=month).first()
    transfer, advance = (misc.transfer_amount, misc.advance) if misc else (Decimal(0), Decimal(0))
    gross = allowances + special + overtime + night + holiday_work + bonus + mission + transfer
    insurable = Decimal(0)
    ins_emp = ins_org = Decimal(0)
    if emp.insurance_type != 'none':
        insurable = allowances + special + overtime + night + holiday_work + bonus
        floor = (calc.min_daily_wage or cfg.min_daily_wage) * days * factor
        insurable = max(insurable, _round(floor))
        if cfg.insurance_ceiling > 0:
            insurable = min(insurable, cfg.insurance_ceiling)
        ins_emp = _round(insurable * (calc.insurance_employee_pct or cfg.insurance_employee_pct) / 100)
        ins_org = _round(insurable * ((calc.insurance_employer_pct or cfg.insurance_employer_pct)
                                      + cfg.unemployment_pct) / 100)
    medical = calc.medical_main + calc.medical_dep1 + calc.medical_dep2 + calc.medical_dep3
    debts = sum((a for _, a in debts_due(emp, year, month)), Decimal(0)) + _special_debt_total(emp, year, month)
    fields = dict(allowances=allowances, special_allowances=special, overtime=overtime, night_work=night,
                  holiday_work=holiday_work, bonus=bonus, mission=mission, misc_transfer=transfer, gross=gross,
                  insurable=insurable, insurance_employee=ins_emp, insurance_org=ins_org, medical=medical,
                  supplementary=calc.supplementary_amount, life_insurance=calc.life_insurance_employee,
                  housing=calc.housing_installment, debts=debts, welfare=welfare, advance=advance, tax=calc.tax_amount)
    fields['deductions'] = sum(fields[k] for k in ('insurance_employee', 'medical', 'supplementary', 'life_insurance',
                                                   'housing', 'debts', 'welfare', 'advance', 'tax'))
    fields['net'] = gross - fields['deductions']
    if fields['net'] < 0:
        raise Invalid(f'خالص پرداختی «{emp.full_name}» منفی می‌شود؛ کسورات یا ورودی‌های ماه را بررسی کنید.')
    return fields


def runs_for(actor):
    return PayrollRun.objects.filter(municipality=municipality_of(actor))


def get_run(actor, pk):
    return _own(municipality_of(actor), PayrollRun.objects.filter(pk=pk).first())


def run_payroll(actor, year, month):
    """Compute (or recompute) the draft payroll of a month for every active employee in service."""
    muni = municipality_of(actor)
    year, month = _period(year, month)
    cfg = settings_of(actor)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        run = PayrollRun.objects.filter(municipality=muni, year=year, month=month).first()
        if run and run.status == 'final':
            raise Conflict('حقوق این ماه قطعی شده است.')
        staff = [e for e in Employee.objects.filter(municipality=muni, active=True) if _in_service(e, year, month)]
        if not staff:
            raise Invalid('پرسنل فعالی برای این ماه وجود ندارد.')
        slips = [(e, calculate(e, year, month, cfg)) for e in staff]
        if run is None:
            run = PayrollRun.objects.create(municipality=muni, year=year, month=month, created_by=actor)
        else:
            run.slips.all().delete()
        PayrollSlip.objects.bulk_create([PayrollSlip(run=run, employee=e, **f) for e, f in slips])
    return run


def finalize_run(actor, run):
    muni = municipality_of(actor)
    _own(muni, run)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        run = _locked(PayrollRun, run.pk)
        if run.status == 'final':
            raise Conflict('این ماه قبلاً قطعی شده است.')
        if PayrollRun.objects.filter(municipality=muni, status='draft').filter(
                Q(year__lt=run.year) | Q(year=run.year, month__lt=run.month)).exists():
            raise Conflict('ماه‌های قبل از این هنوز قطعی نشده‌اند؛ ابتدا آن‌ها را قطعی کنید.')
        for slip in run.slips.select_related('employee'):
            for debt, amount in debts_due(slip.employee, run.year, run.month):
                debt.paid += amount
                debt.save(update_fields=['paid'])
        run.status, run.finalized_at = 'final', timezone.now()
        run.save(update_fields=['status', 'finalized_at'])
    return run


def delete_run(actor, run):
    _own(municipality_of(actor), run)
    run.refresh_from_db()
    if run.status == 'final':
        raise Conflict('محاسبه قطعی حذف نمی‌شود.')
    run.delete()


def mark_uploaded(actor, run, what):
    _own(municipality_of(actor), run)
    if what not in ('insurance', 'tax'):
        raise Invalid('نوع لیست نامعتبر است.')
    setattr(run, f'{what}_uploaded', True)
    run.save(update_fields=[f'{what}_uploaded'])


def run_totals(run):
    agg = run.slips.aggregate(gross=Sum('gross'), deductions=Sum('deductions'), net=Sum('net'),
                              ins_emp=Sum('insurance_employee'), ins_org=Sum('insurance_org'), tax=Sum('tax'))
    return {k: v or 0 for k, v in agg.items()}


# ---- daily workers ------------------------------------------------------------------------------------------------

def workers(actor):
    return DailyWorker.objects.filter(municipality=municipality_of(actor))


def add_worker(actor, **values):
    muni = municipality_of(actor)
    values['national_id'] = _check_national_id(values.get('national_id'))
    for name, label in (('first_name', 'نام'), ('last_name', 'نام خانوادگی')):
        values[name] = _text(values.get(name), label)[:100]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if DailyWorker.objects.filter(municipality=muni, national_id=values['national_id']).exists():
            raise Conflict('کارگری با این شماره ملی قبلاً ثبت شده است.')
        row = (DailyWorker.objects.filter(municipality=muni).order_by('-row').values_list('row', flat=True).first() or 0) + 1
        return DailyWorker.objects.create(municipality=muni, row=row, **values)


def months_for(actor, year, month):
    year, month = _period(year, month)
    return DailyWorkerMonth.objects.filter(worker__municipality=municipality_of(actor), year=year,
                                           month=month).select_related('worker')


def record_worker_month(actor, worker, year, month, *, daily_wage, days, overtime_hours=0, housing=0, grocery=0,
                        advance=0, insurance_employee=0, insurance_org=0, tax_pct=0, pay_date=None):
    muni = municipality_of(actor)
    _own(muni, worker)
    year, month = _period(year, month)
    cfg = settings_of(actor)
    daily_wage = _amount(daily_wage)
    days, overtime_hours, tax_pct = (_num(days, 'روز کارکرد', maximum=31), _num(overtime_hours, 'اضافه کار', maximum=744),
                                     _num(tax_pct, 'درصد مالیات', maximum=100))
    if daily_wage <= 0 or days <= 0:
        raise Invalid('دستمزد روزانه و روز کارکرد باید بیشتر از صفر باشد.')
    housing, grocery, advance = _amount(housing), _amount(grocery), _amount(advance)
    ins_emp, ins_org = _amount(insurance_employee), _amount(insurance_org)
    gross = _round(daily_wage * days + overtime_hours * daily_wage / cfg.hours_per_day * cfg.overtime_multiplier
                   + housing + grocery)
    tax = _round(gross * tax_pct / 100)
    net = gross - ins_emp - advance - tax
    if net < 0:
        raise Invalid('خالص پرداختی منفی می‌شود؛ کسورات را بررسی کنید.')
    with transaction.atomic():
        _locked(Municipality, muni.id)
        obj, _ = DailyWorkerMonth.objects.update_or_create(
            worker=worker, year=year, month=month,
            defaults=dict(daily_wage=daily_wage, days=days, overtime_hours=overtime_hours, housing=housing,
                          grocery=grocery, advance=advance, insurance_employee=ins_emp, insurance_org=ins_org,
                          tax_pct=tax_pct, pay_date=pay_date, gross=gross, tax=tax, net=net))
    return obj


def delete_worker_month(actor, row):
    _own(municipality_of(actor), row.worker)
    row.delete()


# ---- Eidi bonus ---------------------------------------------------------------------------------------------------

def eidi_settings(actor, year):
    return EidiSetting.objects.filter(municipality=municipality_of(actor), year=year)


def set_eidi_setting(actor, year, group, *, fixed_amount, cap=0, annual_days=360, advance=0):
    muni = municipality_of(actor)
    year, _ = _period(year, 1)
    if group not in GROUPS:
        raise Invalid('گروه محاسباتی نامعتبر است.')
    fixed, cap, advance = _amount(fixed_amount), _amount(cap), _amount(advance)
    annual_days = int(_num(annual_days, 'کارکرد سالانه', maximum=366))
    if annual_days < 1 or fixed <= 0:
        raise Invalid('مقدار ثابت و کارکرد سالانه باید بیشتر از صفر باشد.')
    obj, _ = EidiSetting.objects.update_or_create(
        municipality=muni, year=year, calc_group=group,
        defaults=dict(fixed_amount=fixed, cap=cap, annual_days=annual_days, advance=advance))
    return obj


def eidi_records(actor, year):
    return EidiRecord.objects.filter(employee__municipality=municipality_of(actor), year=year).select_related('employee')


def compute_eidi(actor, year, worked=None, only=None):
    """Eidi of every active employee whose group has a setting for the year. `worked` = {employee_id: (worked, absent, sick)}
    overrides the default of a full year; `only` limits it to one employee. amount = min(cap, fixed x (worked - absent) / annual days) - advance, never below 0."""
    muni = municipality_of(actor)
    year, _ = _period(year, 1)
    worked = worked or {}
    settings = {s.calc_group: s for s in EidiSetting.objects.filter(municipality=muni, year=year)}
    if not settings:
        raise Invalid('برای این سال، اطلاعات عیدی هیچ گروهی ثبت نشده است.')
    count = 0
    with transaction.atomic():
        _locked(Municipality, muni.id)
        staff = Employee.objects.filter(municipality=muni, active=True, calc_group__in=settings)
        for emp in staff.filter(pk=only) if only else staff:
            s = settings[emp.calc_group]
            w, a, sick = (_num(x, 'کارکرد') for x in worked.get(emp.id, (s.annual_days, 0, 0)))
            if w > s.annual_days or a > w:
                raise Invalid(f'کارکرد «{emp.full_name}» نامعتبر است.')
            amount = s.fixed_amount * (w - a) / s.annual_days
            if s.cap > 0:
                amount = min(amount, s.cap)
            amount = max(_round(amount) - s.advance, Decimal(0))
            EidiRecord.objects.update_or_create(employee=emp, year=year, defaults=dict(
                worked_days=w, absent_days=a, sick_days=sick, amount=amount))
            count += 1
    return count
