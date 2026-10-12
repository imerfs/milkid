"""Accountant workspace pages for payroll (حقوق و دستمزد). Presentation only: rules are in main/accounting/payroll.

The period (Jalali year and month) travels in the URL of every action and in the `py`/`pm` filters of the pages.
"""
import jdatetime
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from main.accounting import formspec, ledger, payroll
from main.accounting.formspec import Field
from main.accounting.parse import jalali_str
from main.models import CostCenter, Employee
from main.models_payroll import CALC_GROUPS, LIST_TITLES, MONTHS
from main.office.errors import Invalid, OfficeError
from main.views.accounting_finance import _act, _form_modal, _modal, _reg, _url
from main.views.accounting_panel import _done, _failed
from main.views.accounting_views import _guard

GROUP_FIELD = Field('calc_group', 'گروه محاسباتی', 'select', choices=CALC_GROUPS, size=2)
MONTH_NAMES = dict(MONTHS)
GENDERS, MARITAL, INSURANCES = Employee.GENDERS, Employee.MARITAL, Employee.INSURANCES


def _num(name, label, size=1, required=False):
    return Field(name, label, 'pct', required=required, size=size)


def _int(name, label, size=1):
    return Field(name, label, 'text', required=False, size=size, maxlength=3)


def _txt(name, label, size=2, required=False, maxlength=100):
    return Field(name, label, 'text', required=required, size=size, maxlength=maxlength)


def _period(request):
    now = jdatetime.date.today()
    g = request.GET
    try:
        year, month = int(g.get('py') or now.year), int(g.get('pm') or now.month)
        if not (1300 <= year <= 1500 and 1 <= month <= 12):
            raise ValueError
    except ValueError:
        year, month = now.year, now.month
    return year, month


def _per(year, month=None):
    return {'year': year, 'month': month, 'months': MONTHS}


def _edit(request, *, title, fields, action, save, values=None, done='ذخیره شد.', subtitle='', back_url=None):
    """Show a form in the dialog; on POST parse it, call save(data) and close, or show the error on the form."""
    kw = dict(title=title, fields=fields, action=action, subtitle=subtitle, extra={'back_url': back_url} if back_url else None)
    if request.method != 'POST':
        return _form_modal(request, values=values, **kw)
    try:
        save(formspec.parse(ledger.municipality_of(request.user), fields, request.POST))
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done(done)


def _post_action(request, call, message):
    try:
        call()
    except OfficeError as exc:
        return _failed(exc)
    return _done(message)


def _month_label(year, month):
    return f'{MONTH_NAMES[month]} {year}'.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


# ---------- tabs ----------

def tab_pstaff(request, year, ctx):
    rows = []
    for e in payroll.employees(request.user).select_related('cost_center'):
        rows.append({'cells': [e.code, e.full_name, e.national_id, e.get_calc_group_display(), e.list_title, e.job_title,
                               ('فعال', 'ok') if e.active else ('غیرفعال', 'warn')],
                     'actions': [_act('ویرایش', _url('acc_p_emp_edit', e.id), 'modal', 'pen'),
                                 _act('مزایا', _url('acc_p_emp_allowances', e.id), 'modal', 'list'),
                                 _act('بدهی‌ها', _url('acc_p_emp_debts', e.id), 'modal', 'hand-holding-dollar'),
                                 _act('حذف', _url('acc_p_emp_delete', e.id), 'post', 'trash', 'bad', 'این فرد حذف شود؟')]})
    _reg(ctx, ['شماره', 'نام', 'شماره ملی', 'گروه محاسباتی', 'عنوان لیست', 'شغل', 'وضعیت'], rows,
         empty='پرسنلی ثبت نشده است.', icon='users', new_url=_url('acc_p_emp_new'), new_label='پرسنل جدید')


def tab_pcalc(request, year, ctx):
    rows = []
    for e in payroll.employees(request.user, active=True):
        c = payroll.calc_of(e)
        rows.append({'cells': [e.code, e.full_name, e.get_calc_group_display(), ('money', c.mission_day_rate),
                               ('money', c.overtime_rate), ('money', c.housing_installment), ('money', c.tax_amount)],
                     'actions': [_act('ویرایش', _url('acc_p_emp_calc', e.id), 'modal', 'pen')]})
    _reg(ctx, ['شماره', 'نام', 'گروه', 'روز ماموریت', 'ساعت اضافه کار', 'قسط مسکن', 'مالیات ماهانه'], rows,
         empty='پرسنل فعالی وجود ندارد.', icon='sliders')


def tab_pattendance(request, year, ctx):
    py, pm = _period(request)
    got = {a.employee_id: a for a in payroll.attendance_for(request.user, py, pm)}
    rows = []
    for e in payroll.employees(request.user, active=True):
        a = got.get(e.id)
        cells = [e.code, e.full_name] + ([a.worked_days or '—', a.absent_days, a.sick_days, a.ot_normal, a.ot_holiday,
                                          a.night_hours] if a else ['—'] * 6)
        acts = [_act('ثبت کارکرد' if not a else 'ویرایش', _url('acc_p_attendance', py, pm, e.id), 'modal', 'pen')]
        if a:
            acts.append(_act('حذف', _url('acc_p_attendance_delete', a.id), 'post', 'trash', 'bad', 'کارکرد این ماه حذف شود؟'))
        rows.append({'cells': cells, 'actions': acts})
    _reg(ctx, ['شماره', 'نام', 'کارکرد (روز)', 'غیبت', 'استعلاجی', 'اضافه کار', 'اضافه کار تعطیل', 'شب کاری'], rows,
         empty='پرسنل فعالی وجود ندارد.', icon='clock', filters={'period': _per(py, pm)})


def tab_pmission(request, year, ctx):
    rows = [{'cells': [m.employee.full_name, m.order_no, jalali_str(m.start_date), jalali_str(m.end_date), m.days,
                       f'{m.origin} به {m.destination}', ('money', m.misc_cost)],
             'actions': [_act('حذف', _url('acc_p_mission_delete', m.id), 'post', 'trash', 'bad', 'این ماموریت حذف شود؟')]}
            for m in payroll.missions_for(request.user)]
    _reg(ctx, ['نام', 'شماره حکم', 'شروع', 'خاتمه', 'روز', 'مسیر', 'هزینه متفرقه'], rows,
         empty='ماموریتی ثبت نشده است.', icon='plane', new_url=_url('acc_p_mission_new'), new_label='ماموریت جدید')


def tab_pspecialallow(request, year, ctx):
    rows = [{'cells': [s.get_calc_group_display(), s.title, ('money', s.amount)],
             'actions': [_act('حذف', _url('acc_p_special_delete', 'allowance', s.id), 'post', 'trash', 'bad', 'حذف شود؟')]}
            for s in payroll.special_allowances(request.user)]
    _reg(ctx, ['گروه محاسباتی', 'عنوان مزایا', 'مبلغ ماهانه'], rows, empty='مزایای مخصوصی ثبت نشده است.', icon='gift',
         new_url=_url('acc_p_special_new', 'allowance'), new_label='مزایای مخصوص جدید')


def tab_pspecialdebt(request, year, ctx):
    rows = [{'cells': [s.get_calc_group_display(), s.title, ('money', s.installment), f'{s.months} ماه',
                       _month_label(s.start_year, s.start_month)],
             'actions': [_act('حذف', _url('acc_p_special_delete', 'debt', s.id), 'post', 'trash', 'bad', 'حذف شود؟')]}
            for s in payroll.special_debts(request.user)]
    _reg(ctx, ['گروه محاسباتی', 'عنوان بدهی', 'قسط ماهانه', 'مدت', 'شروع'], rows, empty='بدهی مخصوصی ثبت نشده است.',
         icon='file-invoice-dollar', new_url=_url('acc_p_special_new', 'debt'), new_label='بدهی مخصوص جدید')


def tab_pmisc(request, year, ctx):
    py, pm = _period(request)
    got = {m.employee_id: m for m in payroll.misc_for(request.user, py, pm)}
    rows = []
    for e in payroll.employees(request.user, active=True):
        m = got.get(e.id)
        rows.append({'cells': [e.code, e.full_name, ('money', m.transfer_amount if m else 0), ('money', m.advance if m else 0)],
                     'actions': [_act('ثبت' if not m else 'ویرایش', _url('acc_p_misc', py, pm, e.id), 'modal', 'pen')]})
    _reg(ctx, ['شماره', 'نام', 'مبلغ واریزی', 'علی‌الحساب'], rows, empty='پرسنل فعالی وجود ندارد.', icon='wallet',
         filters={'period': _per(py, pm)})


def tab_pworkers(request, year, ctx):
    py, pm = _period(request)
    got = {m.worker_id: m for m in payroll.months_for(request.user, py, pm)}
    rows = []
    for w in payroll.workers(request.user):
        m = got.get(w.id)
        cells = [w.row, w.full_name, w.national_id] + ([('money', m.daily_wage), m.days, ('money', m.gross), ('money', m.net)]
                                                      if m else ['—', '—', '—', '—'])
        acts = [_act('ثبت کارکرد' if not m else 'ویرایش', _url('acc_p_worker_month', py, pm, w.id), 'modal', 'pen')]
        if m:
            acts.append(_act('حذف کارکرد', _url('acc_p_worker_month_delete', m.id), 'post', 'trash', 'bad', 'حذف شود؟'))
        rows.append({'cells': cells, 'actions': acts})
    _reg(ctx, ['ردیف', 'نام', 'شماره ملی', 'دستمزد روزانه', 'روز', 'ناخالص', 'خالص'], rows,
         empty='کارگر روزمزدی ثبت نشده است.', icon='helmet-safe', new_url=_url('acc_p_worker_new'),
         new_label='کارگر جدید', filters={'period': _per(py, pm)})


def tab_peidi(request, year, ctx):
    py, _ = _period(request)
    settings = [[s.get_calc_group_display(), ('money', s.fixed_amount), ('money', s.cap), s.annual_days, ('money', s.advance)]
                for s in payroll.eidi_settings(request.user, py)]
    rows = [{'cells': [r.employee.code, r.employee.full_name, r.worked_days, r.absent_days, r.sick_days, ('money', r.amount)],
             'actions': [_act('کارکرد', _url('acc_p_eidi_days', py, r.employee_id), 'modal', 'pen')]}
            for r in payroll.eidi_records(request.user, py)]
    _reg(ctx, ['شماره', 'نام', 'کارکرد', 'غیبت', 'استعلاجی', 'عیدی (ریال)'], rows,
         empty='عیدی این سال هنوز محاسبه نشده است.', icon='gift', filters={'period': _per(py)},
         intro={'title': 'تنظیم عیدی گروه‌ها', 'cols': ['گروه', 'مقدار ثابت', 'سقف', 'کارکرد سالانه', 'علی‌الحساب'],
                'empty': 'برای این سال تنظیمی ثبت نشده است.', 'rows': settings},
         buttons=[{'label': 'تنظیم عیدی گروه', 'url': _url('acc_p_eidi_setting', py), 'kind': 'modal', 'icon': 'sliders', 'cls': ''},
                  {'label': 'محاسبه عیدی', 'url': _url('acc_p_eidi_compute', py), 'kind': 'post', 'icon': 'calculator',
                   'cls': 'ac-btn-brand', 'confirm': 'عیدی همه پرسنل محاسبه (و محاسبه قبلی بازنویسی) شود؟'}])


def tab_prun(request, year, ctx):
    py, pm = _period(request)
    run = payroll.runs_for(request.user).filter(year=py, month=pm).first()
    rows, intro, buttons = [], None, []
    if run:
        for s in run.slips.select_related('employee'):
            rows.append({'cells': [s.employee.code, s.employee.full_name, ('money', s.gross), ('money', s.insurance_employee),
                                   ('money', s.debts), ('money', s.tax), ('money', s.deductions), ('money', s.net)],
                         'actions': [_act('فیش', _url('acc_p_slip', s.id), 'modal', 'file-invoice')]})
        t = payroll.run_totals(run)
        intro = {'title': f'حقوق {_month_label(py, pm)} — {run.get_status_display()}',
                 'cols': ['جمع ناخالص', 'جمع کسورات', 'جمع خالص پرداختی', 'بیمه سهم فرد', 'بیمه سهم کارفرما', 'مالیات'],
                 'empty': '', 'rows': [[('money', t['gross']), ('money', t['deductions']), ('money', t['net']),
                                         ('money', t['ins_emp']), ('money', t['ins_org']), ('money', t['tax'])]]}
        buttons.append({'label': 'خروجی اکسل', 'url': _url('acc_p_run_export', run.id), 'kind': 'link', 'icon': 'file-excel', 'cls': ''})
        if run.status == 'draft':
            buttons.append({'label': 'قطعی کردن', 'url': _url('acc_p_run_finalize', run.id), 'kind': 'post', 'icon': 'lock',
                            'cls': '', 'confirm': 'پس از قطعی شدن، ورودی‌ها و فیش‌های این ماه تغییر نمی‌کند و اقساط بدهی کسر می‌شود. ادامه؟'})
            buttons.append({'label': 'حذف محاسبه', 'url': _url('acc_p_run_delete', run.id), 'kind': 'post', 'icon': 'trash',
                            'cls': '', 'confirm': 'محاسبه این ماه حذف شود؟'})
    if not run or run.status == 'draft':
        buttons.insert(0, {'label': 'محاسبه حقوق', 'url': _url('acc_p_run', py, pm), 'kind': 'post', 'icon': 'calculator',
                           'cls': 'ac-btn-brand', 'confirm': ''})
    _reg(ctx, ['شماره', 'نام', 'ناخالص', 'بیمه سهم فرد', 'بدهی', 'مالیات', 'جمع کسورات', 'خالص پرداختی'], rows,
         empty='حقوق این ماه هنوز محاسبه نشده است.', icon='money-bill-wave', filters={'period': _per(py, pm)},
         intro=intro, buttons=buttons)


def tab_psettings(request, year, ctx):
    s = payroll.settings_of(request.user)
    rows = [{'cells': [label, str(value)], 'actions': []} for label, value in [
        ('روزهای ماه برای محاسبه', s.month_days), ('ساعت کار روزانه', s.hours_per_day),
        ('ضریب اضافه کار', s.overtime_multiplier), ('ضریب جمعه‌کاری و تعطیل', s.holiday_multiplier),
        ('درصد شب کاری', s.night_pct), ('٪ بیمه سهم فرد', s.insurance_employee_pct),
        ('٪ بیمه سهم کارفرما', s.insurance_employer_pct), ('٪ بیمه بیکاری', s.unemployment_pct),
        ('سقف ماهانه مشمول بیمه (ریال)', f'{s.insurance_ceiling:,}'), ('حداقل دستمزد روزانه (ریال)', f'{s.min_daily_wage:,}')]]
    _reg(ctx, ['مورد', 'مقدار'], rows, empty='', icon='gear',
         buttons=[{'label': 'ویرایش تنظیمات', 'url': _url('acc_p_paysettings'), 'kind': 'modal', 'icon': 'pen', 'cls': 'ac-btn-brand'},
                  {'label': 'عنوان مزایا', 'url': _url('acc_p_paytitles'), 'kind': 'modal', 'icon': 'list', 'cls': ''}])


BUILDERS = {'pstaff': tab_pstaff, 'pcalc': tab_pcalc, 'pattendance': tab_pattendance, 'pmission': tab_pmission,
            'pspecialallow': tab_pspecialallow, 'pspecialdebt': tab_pspecialdebt, 'pmisc': tab_pmisc,
            'pworkers': tab_pworkers, 'peidi': tab_peidi, 'prun': tab_prun, 'psettings': tab_psettings}


# ---------- employees ----------

def _emp_fields(new):
    return [
        _txt('first_name', 'نام', 1, True), _txt('last_name', 'نام خانوادگی', 1, True), _txt('father_name', 'نام پدر', 1),
        _txt('national_id', 'شماره ملی', 1, True, 10),
        *([Field('code', 'شماره شناسایی', 'text', required=False, size=1, maxlength=6, placeholder='خودکار')] if new else []),
        _txt('id_card_no', 'شماره شناسنامه', 1, maxlength=20),
        Field('birth_date', 'تاریخ تولد', 'date', required=False, size=1),
        Field('gender', 'جنسیت', 'select', choices=GENDERS, size=1), Field('marital', 'تاهل', 'select', choices=MARITAL, size=1),
        _int('children', 'تعداد اولاد'), _txt('veteran_status', 'وضعیت ایثارگری', 1), _txt('service_status', 'وضعیت خدمتی', 1),
        GROUP_FIELD,
        Field('list_title', 'عنوان لیست', 'select', choices=[(t, t) for t in LIST_TITLES], size=2),
        _txt('org_status', 'وضعیت سازمانی', 1, maxlength=50), _txt('employment_type', 'نوع استخدام', 1, maxlength=50),
        _txt('post_level', 'سطح پست', 1, maxlength=50), _txt('job_rank', 'رتبه شغلی', 1, maxlength=50),
        _txt('education', 'مدرک تحصیلی', 1, maxlength=50), _txt('job_title', 'عنوان شغل', 2, True),
        _txt('org_unit', 'واحد سازمانی', 2),
        Field('cost_center', 'مرکز هزینه', 'fk', model=CostCenter, required=False, size=2, label_of=lambda o: f'{o.code} {o.title}'),
        Field('start_date', 'تاریخ شروع خدمت', 'date', size=1), Field('end_date', 'تاریخ پایان خدمت', 'date', required=False, size=1),
        Field('insurance_type', 'نوع بیمه', 'select', choices=INSURANCES, size=1), _txt('insurance_no', 'شماره بیمه‌گری', 1, maxlength=20),
        _int('ins_main', 'بیمه عادی: اصلی'), _int('ins_dep1', 'تبعی یک'), _int('ins_dep2', 'تبعی دو'), _int('ins_dep3', 'تبعی سه'),
        _int('supp_normal', 'تکمیلی عادی'), _int('supp_special1', 'خاص یک'), _int('supp_special2', 'خاص دو'), _int('supp_special3', 'خاص سه'),
        _txt('bank_name', 'نام بانک', 1, maxlength=60), _txt('account_type', 'نوع حساب', 1, maxlength=40),
        _txt('account_main', 'حساب اصلی', 1, maxlength=40), _txt('account_misc', 'حساب متفرقه', 1, maxlength=40)]


def _code(data):
    code = data.pop('code', None)
    if code:
        if not str(code).isdigit():
            raise Invalid('شماره شناسایی باید عدد باشد.')
        data['code'] = int(code)
    return data


@_guard()
def acc_p_emp_new(request):
    fields = _emp_fields(True)
    return _edit(request, title='پرسنل جدید', fields=fields, action=_url('acc_p_emp_new'),
                 save=lambda d: payroll.add_employee(request.user, **_code(d)), done='پرسنل ثبت شد.',
                 values={'gender': 'm', 'marital': 'single', 'insurance_type': 'social', 'ins_main': 1, 'veteran_status': 'عادی'})


@_guard()
def acc_p_emp_edit(request, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    fields = _emp_fields(False)
    return _edit(request, title=f'ویرایش {emp.full_name}', fields=fields, action=_url('acc_p_emp_edit', emp.id),
                 save=lambda d: payroll.update_employee(request.user, emp, **d), values=formspec.initial(fields, emp))


@_guard()
@require_POST
def acc_p_emp_delete(request, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    return _post_action(request, lambda: payroll.delete_employee(request.user, emp), 'حذف شد.')


@_guard()
def acc_p_emp_allowances(request, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    titles = payroll.titles_of(request.user)
    fields = [Field(f'a{s}', titles[s], 'amount', required=False, size=2) for s in payroll.SLOTS]
    saved = dict(emp.allowances.values_list('slot', 'amount'))

    def save(data):
        payroll.set_allowances(request.user, emp, {s: data[f'a{s}'] for s in payroll.SLOTS})
    return _edit(request, title=f'مزایای ماهانه {emp.full_name}', fields=fields, action=_url('acc_p_emp_allowances', emp.id),
                 save=save, subtitle='مبلغ ماهانه هر ردیف (ریال). ردیف اول، حقوق پایه است و مبنای اضافه کار می‌شود.',
                 values={f'a{s}': saved.get(s, '') for s in payroll.SLOTS})


CALC_FIELDS = [Field(n, label, 'amount', required=False, size=2) for n, label in [
    ('mission_day_rate', 'یک روز ماموریت'), ('overtime_rate', 'یک ساعت اضافه کار عادی'),
    ('holiday_overtime_rate', 'یک ساعت اضافه کار تعطیل'), ('min_daily_wage', 'حداقل دستمزد روزانه'),
    ('life_insurance_employee', 'بیمه عمر سهم فرد'), ('life_insurance_org', 'بیمه عمر سهم سازمان'),
    ('housing_installment', 'قسط مسکن ماهانه'), ('supplementary_amount', 'بیمه تکمیلی ماهانه'),
    ('medical_main', 'بیمه درمانی اصلی'), ('medical_dep1', 'بیمه درمانی تبعی یک'), ('medical_dep2', 'بیمه درمانی تبعی دو'),
    ('medical_dep3', 'بیمه درمانی تبعی سه'), ('tax_amount', 'مالیات ماهانه (از سامانه مالیاتی)')]] + [
    _num('insurance_employee_pct', '٪ بیمه سهم فرد', 2), _num('insurance_employer_pct', '٪ بیمه سهم سازمان', 2)]


@_guard()
def acc_p_emp_calc(request, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    return _edit(request, title=f'محاسبات فردی {emp.full_name}', fields=CALC_FIELDS, action=_url('acc_p_emp_calc', emp.id),
                 subtitle='مقدار صفر یعنی از تنظیمات عمومی حقوق استفاده شود. مالیات حقوق محاسبه نمی‌شود؛ مبلغ سامانه مالیاتی را وارد کنید.',
                 save=lambda d: payroll.set_personal_calc(request.user, emp, **d),
                 values=formspec.initial(CALC_FIELDS, payroll.calc_of(emp)))


# ---------- debts ----------

DEBT_FIELDS = [_txt('title', 'عنوان بدهی', 2, True), Field('total', 'کل بدهی (ریال)', 'amount', size=1),
               Field('installment', 'قسط ماهانه سهم فرد', 'amount', size=1),
               Field('org_share', 'سهم سازمان', 'amount', required=False, size=1),
               Field('start_year', 'سال شروع', 'text', size=1, maxlength=4), Field('start_month', 'ماه شروع', 'select', choices=[(str(k), v) for k, v in MONTHS], size=1),
               _txt('note', 'توضیحات', 4, maxlength=300)]


def _debts_modal(request, emp, notice=None, error=None, status=200):
    emp = payroll.get_employee(request.user, emp.pk)
    return _modal(request, 'emp_debts.html', {'emp': emp, 'debts': emp.debts.all(), 'error': error, 'notice': notice,
                                              'months': MONTH_NAMES}, status)


@_guard()
def acc_p_emp_debts(request, emp_id):
    return _debts_modal(request, payroll.get_employee(request.user, emp_id))


@_guard()
def acc_p_debt_new(request, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    now = jdatetime.date.today()
    return _edit(request, title=f'بدهی جدید {emp.full_name}', fields=DEBT_FIELDS, action=_url('acc_p_debt_new', emp.id),
                 save=lambda d: payroll.add_debt(request.user, emp, **d), back_url=_url('acc_p_emp_debts', emp.id),
                 values={'start_year': now.year, 'start_month': now.month}, done='بدهی ثبت شد.')


def _debt_of(request, debt_id):
    from main.models import EmployeeDebt
    debt = EmployeeDebt.objects.filter(pk=debt_id, employee__municipality=ledger.municipality_of(request.user)).first()
    if debt is None:
        raise Http404()
    return debt


@_guard()
@require_POST
def acc_p_debt_delete(request, debt_id):
    debt = _debt_of(request, debt_id)
    try:
        payroll.delete_debt(request.user, debt)
    except OfficeError as exc:
        return _debts_modal(request, debt.employee, error=str(exc), status=exc.status)
    return _debts_modal(request, debt.employee, notice='بدهی حذف شد.')


@_guard()
@require_POST
def acc_p_debt_toggle(request, debt_id):
    debt = _debt_of(request, debt_id)
    payroll.set_debt_active(request.user, debt, not debt.active)
    return _debts_modal(request, debt.employee, notice='وضعیت بدهی تغییر کرد.')


# ---------- monthly inputs ----------

ATT_FIELDS = [_num('worked_days', 'کارکرد (روز؛ خالی = کل ماه)', 2), _num('absent_days', 'غیبت (روز)', 2),
              _num('sick_days', 'استعلاجی (روز)', 2), _num('ot_normal', 'اضافه کار عادی (ساعت)', 2),
              _num('ot_holiday', 'اضافه کار تعطیل (ساعت)', 2), _num('ot_incentive', 'اضافه کار تشویقی (ساعت)', 2),
              _num('holiday_work_days', 'جمعه‌کاری (روز)', 2), _num('night_hours', 'شب کاری (ساعت)', 2),
              _num('bonus_pct', 'کارانه (٪ مزایا)', 2), _num('welfare_pct', 'رفاهیات (٪ کسر)', 2)]


@_guard()
def acc_p_attendance(request, py, pm, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    row = payroll.attendance_for(request.user, py, pm).filter(employee=emp).first()
    return _edit(request, title=f'کارکرد {emp.full_name} — {_month_label(py, pm)}', fields=ATT_FIELDS,
                 action=_url('acc_p_attendance', py, pm, emp.id), save=lambda d: payroll.set_attendance(request.user, emp, py, pm, **d),
                 values=formspec.initial(ATT_FIELDS, row) if row else None)


@_guard()
@require_POST
def acc_p_attendance_delete(request, row_id):
    row = payroll.MonthlyAttendance.objects.filter(pk=row_id, employee__municipality=ledger.municipality_of(request.user)).first()
    if row is None:
        raise Http404()
    return _post_action(request, lambda: payroll.delete_attendance(request.user, row), 'حذف شد.')


MISSION_FIELDS = [Field('employee', 'پرسنل', 'fk', model=Employee, where={'active': True}, size=2, label_of=lambda o: o.full_name),
                  _txt('order_no', 'شماره حکم', 1, True, 40), Field('order_date', 'تاریخ حکم', 'date', size=1),
                  Field('start_date', 'تاریخ شروع', 'date', size=1), Field('end_date', 'تاریخ خاتمه', 'date', size=1),
                  _txt('origin', 'شهر مبدا', 1, True, 80), _txt('destination', 'شهر مقصد', 1, True, 80),
                  _int('distance_km', 'فاصله (کیلومتر)'), Field('driving_right', 'مسئول حق رانندگی', 'bool', size=1),
                  Field('bad_weather', 'بدی آب و هوا (ریال)', 'amount', required=False, size=2),
                  Field('misc_cost', 'هزینه متفرقه (ریال)', 'amount', required=False, size=2)]


@_guard()
def acc_p_mission_new(request):
    def save(d):
        emp = d.pop('employee')
        payroll.add_mission(request.user, emp, **d)
    return _edit(request, title='ماموریت جدید', fields=MISSION_FIELDS, action=_url('acc_p_mission_new'), save=save,
                 subtitle='مبلغ ماموریت = روزهای ماموریت × نرخ روز ماموریت فرد (محاسبات فردی) + بدی آب و هوا + هزینه متفرقه، در ماه شروع ماموریت.',
                 done='ماموریت ثبت شد.')


@_guard()
@require_POST
def acc_p_mission_delete(request, mission_id):
    m = payroll.missions_for(request.user).filter(pk=mission_id).first()
    if m is None:
        raise Http404()
    return _post_action(request, lambda: payroll.delete_mission(request.user, m), 'حذف شد.')


@_guard()
def acc_p_special_new(request, kind):
    if kind not in ('allowance', 'debt'):
        raise Http404()
    if kind == 'allowance':
        fields = [GROUP_FIELD, _txt('title', 'عنوان مزایا', 2, True), Field('amount', 'مبلغ ماهانه (ریال)', 'amount', size=2)]
        save = lambda d: payroll.add_special_allowance(request.user, d['calc_group'], d['title'], d['amount'])   # noqa: E731
        title, values = 'مزایای مخصوص جدید', None
    else:
        now = jdatetime.date.today()
        fields = [GROUP_FIELD, _txt('title', 'عنوان بدهی', 2, True), Field('installment', 'قسط ماهانه (ریال)', 'amount', size=2),
                  Field('org_share', 'سهم سازمان', 'amount', required=False, size=2),
                  Field('start_year', 'سال شروع', 'text', size=1, maxlength=4),
                  Field('start_month', 'ماه شروع', 'select', choices=[(str(k), v) for k, v in MONTHS], size=1),
                  Field('months', 'تعداد ماه', 'text', size=2, maxlength=3), _txt('note', 'توضیحات', 4, maxlength=300)]
        save = lambda d: payroll.add_special_debt(request.user, d.pop('calc_group'), d.pop('title'), d.pop('installment'), **d)   # noqa: E731
        title, values = 'بدهی مخصوص جدید', {'start_year': now.year, 'start_month': now.month, 'months': 12}
    return _edit(request, title=title, fields=fields, action=_url('acc_p_special_new', kind), save=save, values=values,
                 subtitle='برای همه پرسنل فعال گروه محاسباتی انتخاب‌شده اعمال می‌شود.', done='ثبت شد.')


@_guard()
@require_POST
def acc_p_special_delete(request, kind, obj_id):
    source = {'allowance': payroll.special_allowances, 'debt': payroll.special_debts}.get(kind)
    obj = source(request.user).filter(pk=obj_id).first() if source else None
    if obj is None:
        raise Http404()
    return _post_action(request, lambda: payroll.delete_special(request.user, obj), 'حذف شد.')


MISC_FIELDS = [Field('transfer_amount', 'مبلغ واریزی (ریال)', 'amount', required=False, size=2),
               Field('advance', 'علی‌الحساب (کسر از حقوق همان ماه)', 'amount', required=False, size=2)]


@_guard()
def acc_p_misc(request, py, pm, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    row = payroll.misc_for(request.user, py, pm).filter(employee=emp).first()
    return _edit(request, title=f'پرداخت متفرقه {emp.full_name} — {_month_label(py, pm)}', fields=MISC_FIELDS,
                 action=_url('acc_p_misc', py, pm, emp.id), save=lambda d: payroll.set_misc(request.user, emp, py, pm, **d),
                 subtitle='واریزی به حقوق افزوده می‌شود و مشمول بیمه نیست. مقدار صفر، ردیف را پاک می‌کند.',
                 values=formspec.initial(MISC_FIELDS, row) if row else None)


# ---------- the monthly run ----------

@_guard()
@require_POST
def acc_p_run(request, py, pm):
    return _post_action(request, lambda: payroll.run_payroll(request.user, py, pm), f'حقوق {_month_label(py, pm)} محاسبه شد.')


@_guard()
@require_POST
def acc_p_run_finalize(request, run_id):
    run = payroll.get_run(request.user, run_id)
    return _post_action(request, lambda: payroll.finalize_run(request.user, run), 'حقوق این ماه قطعی شد.')


@_guard()
@require_POST
def acc_p_run_delete(request, run_id):
    run = payroll.get_run(request.user, run_id)
    return _post_action(request, lambda: payroll.delete_run(request.user, run), 'محاسبه حذف شد.')


@_guard()
def acc_p_slip(request, slip_id):
    slip = payroll.PayrollSlip.objects.select_related('run', 'employee').filter(
        pk=slip_id, run__municipality=ledger.municipality_of(request.user)).first()
    if slip is None:
        raise Http404()
    earn = [('مزایای ماهانه', slip.allowances), ('مزایای مخصوص', slip.special_allowances), ('اضافه کار', slip.overtime),
            ('شب کاری', slip.night_work), ('جمعه‌کاری', slip.holiday_work), ('کارانه', slip.bonus), ('ماموریت', slip.mission),
            ('واریزی متفرقه', slip.misc_transfer)]
    cut = [('بیمه سهم فرد', slip.insurance_employee), ('بیمه درمانی', slip.medical), ('بیمه تکمیلی', slip.supplementary),
           ('بیمه عمر', slip.life_insurance), ('قسط مسکن', slip.housing), ('بدهی‌ها', slip.debts), ('رفاهیات', slip.welfare),
           ('علی‌الحساب', slip.advance), ('مالیات', slip.tax)]
    return _modal(request, 'slip_detail.html', {'slip': slip, 'period': _month_label(slip.run.year, slip.run.month),
                                                'earn': [r for r in earn if r[1]], 'cut': [r for r in cut if r[1]]})


@_guard()
def acc_p_run_export(request, run_id):
    run = payroll.get_run(request.user, run_id)
    wb = Workbook()
    ws = wb.active
    ws.title = f'{run.year}-{run.month:02d}'
    ws.sheet_view.rightToLeft = True
    head = ['شماره', 'نام', 'شماره ملی', 'مزایا', 'اضافه کار', 'ماموریت', 'ناخالص', 'مشمول بیمه', 'بیمه سهم فرد', 'بیمه سهم کارفرما',
            'بدهی', 'علی‌الحساب', 'مالیات', 'جمع کسورات', 'خالص پرداختی', 'حساب']
    ws.append(head)
    for s in run.slips.select_related('employee'):
        e = s.employee
        ws.append([e.code, e.full_name, "'" + e.national_id, int(s.allowances + s.special_allowances), int(s.overtime),
                   int(s.mission), int(s.gross), int(s.insurable), int(s.insurance_employee), int(s.insurance_org),
                   int(s.debts), int(s.advance), int(s.tax), int(s.deductions), int(s.net), e.account_main])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="payroll-{run.year}-{run.month:02d}.xlsx"'
    wb.save(response)
    return response


# ---------- daily workers ----------

WORKER_FIELDS = [_txt('first_name', 'نام', 1, True), _txt('last_name', 'نام خانوادگی', 1, True), _txt('father_name', 'نام پدر', 1),
                 _txt('national_id', 'شماره ملی', 1, True, 10), _txt('id_card_no', 'شماره شناسنامه', 1, maxlength=20),
                 Field('gender', 'جنسیت', 'select', choices=GENDERS, size=1), _txt('insurance_no', 'شماره بیمه‌گری', 1, maxlength=20),
                 _txt('job_title', 'عنوان شغل', 1), _txt('account_no', 'شماره حساب', 2, maxlength=40)]
WM_FIELDS = [Field('daily_wage', 'دستمزد روزانه (ریال)', 'amount', size=2), _num('days', 'روز کارکرد', 2, True),
             _num('overtime_hours', 'ساعت اضافه کار', 2), Field('housing', 'حق مسکن', 'amount', required=False, size=2),
             Field('grocery', 'حق خواربار', 'amount', required=False, size=2), Field('advance', 'علی‌الحساب', 'amount', required=False, size=2),
             Field('insurance_employee', 'بیمه سهم فرد', 'amount', required=False, size=2),
             Field('insurance_org', 'بیمه سهم سازمان', 'amount', required=False, size=2),
             _num('tax_pct', 'درصد مالیات', 2), Field('pay_date', 'تاریخ پرداخت', 'date', required=False, size=2)]


@_guard()
def acc_p_worker_new(request):
    return _edit(request, title='کارگر روزمزد جدید', fields=WORKER_FIELDS, action=_url('acc_p_worker_new'),
                 save=lambda d: payroll.add_worker(request.user, **d), values={'gender': 'm'}, done='کارگر ثبت شد.')


def _worker_of(request, worker_id):
    worker = payroll.workers(request.user).filter(pk=worker_id).first()
    if worker is None:
        raise Http404()
    return worker


@_guard()
def acc_p_worker_month(request, py, pm, worker_id):
    worker = _worker_of(request, worker_id)
    row = payroll.months_for(request.user, py, pm).filter(worker=worker).first()
    return _edit(request, title=f'کارکرد {worker.full_name} — {_month_label(py, pm)}', fields=WM_FIELDS,
                 action=_url('acc_p_worker_month', py, pm, worker.id),
                 subtitle='ناخالص = دستمزد × روز + اضافه کار + مسکن + خواربار؛ خالص = ناخالص − بیمه − علی‌الحساب − مالیات.',
                 save=lambda d: payroll.record_worker_month(request.user, worker, py, pm, **d),
                 values=formspec.initial(WM_FIELDS, row) if row else None)


@_guard()
@require_POST
def acc_p_worker_month_delete(request, row_id):
    row = payroll.DailyWorkerMonth.objects.filter(pk=row_id, worker__municipality=ledger.municipality_of(request.user)).first()
    if row is None:
        raise Http404()
    return _post_action(request, lambda: payroll.delete_worker_month(request.user, row), 'حذف شد.')


# ---------- Eidi ----------

EIDI_SETTING_FIELDS = [GROUP_FIELD, Field('fixed_amount', 'مقدار ثابت (عیدی یک سال کامل، ریال)', 'amount', size=2),
                       Field('cap', 'سقف عیدی (۰ = بدون سقف)', 'amount', required=False, size=2),
                       Field('annual_days', 'کارکرد سالانه (روز)', 'text', required=False, size=1, maxlength=3),
                       Field('advance', 'علی‌الحساب عیدی', 'amount', required=False, size=1)]
EIDI_DAYS = [_num('worked', 'کارکرد (روز)', 2, True), _num('absent', 'غیبت (روز)', 2), _num('sick', 'استعلاجی (روز)', 2)]


@_guard()
def acc_p_eidi_setting(request, py):
    def save(d):
        payroll.set_eidi_setting(request.user, py, d.pop('calc_group'), fixed_amount=d['fixed_amount'], cap=d['cap'],
                                 annual_days=d['annual_days'] or 360, advance=d['advance'])
    return _edit(request, title=f'تنظیم عیدی سال {py}', fields=EIDI_SETTING_FIELDS, action=_url('acc_p_eidi_setting', py),
                 save=save, values={'annual_days': 360},
                 subtitle='عیدی = مقدار ثابت × (کارکرد − غیبت) ÷ کارکرد سالانه، با رعایت سقف، منهای علی‌الحساب.')


@_guard()
@require_POST
def acc_p_eidi_compute(request, py):
    overrides = {r.employee_id: (r.worked_days, r.absent_days, r.sick_days) for r in payroll.eidi_records(request.user, py)}
    return _post_action(request, lambda: payroll.compute_eidi(request.user, py, overrides), f'عیدی سال {py} محاسبه شد.')


@_guard()
def acc_p_eidi_days(request, py, emp_id):
    emp = payroll.get_employee(request.user, emp_id)
    rec = payroll.eidi_records(request.user, py).filter(employee=emp).first()
    if rec is None:
        raise Http404()

    def save(d):
        payroll.compute_eidi(request.user, py, {emp.id: (d['worked'], d['absent'], d['sick'])}, only=emp.id)
    return _edit(request, title=f'کارکرد عیدی {emp.full_name}', fields=EIDI_DAYS, action=_url('acc_p_eidi_days', py, emp.id),
                 save=save, values={'worked': rec.worked_days, 'absent': rec.absent_days, 'sick': rec.sick_days})


# ---------- settings ----------

SETTING_FIELDS = [Field('month_days', 'روزهای ماه برای محاسبه', 'text', size=1, maxlength=2),
                  _num('hours_per_day', 'ساعت کار روزانه', 1, True), _num('overtime_multiplier', 'ضریب اضافه کار', 1, True),
                  _num('holiday_multiplier', 'ضریب جمعه‌کاری و تعطیل', 1, True), _num('night_pct', '٪ شب کاری', 1, True),
                  _num('insurance_employee_pct', '٪ بیمه سهم فرد', 1, True), _num('insurance_employer_pct', '٪ بیمه سهم کارفرما', 1, True),
                  _num('unemployment_pct', '٪ بیمه بیکاری', 1, True),
                  Field('insurance_ceiling', 'سقف ماهانه مشمول بیمه (۰ = بدون سقف)', 'amount', required=False, size=2),
                  Field('min_daily_wage', 'حداقل دستمزد روزانه', 'amount', required=False, size=2)]


@_guard()
def acc_p_paysettings(request):
    return _edit(request, title='تنظیمات حقوق', fields=SETTING_FIELDS, action=_url('acc_p_paysettings'),
                 subtitle='نرخ‌ها طبق مقررات سال جاری تنظیم شود؛ تغییر آن‌ها روی محاسبه‌های قطعی‌نشده اثر می‌گذارد.',
                 save=lambda d: payroll.update_settings(request.user, **d),
                 values=formspec.initial(SETTING_FIELDS, payroll.settings_of(request.user)))


@_guard()
def acc_p_paytitles(request):
    titles = payroll.titles_of(request.user)
    fields = [_txt(f't{s}', f'ردیف {s}', 2, False, 100) for s in payroll.SLOTS]

    def save(d):
        for s in payroll.SLOTS:
            if d[f't{s}'] and d[f't{s}'] != titles[s]:
                payroll.set_title(request.user, s, d[f't{s}'])
    return _edit(request, title='عنوان ردیف‌های مزایا', fields=fields, action=_url('acc_p_paytitles'), save=save,
                 values={f't{s}': titles[s] for s in payroll.SLOTS})
