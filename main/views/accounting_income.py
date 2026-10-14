"""Accountant workspace pages for instalment plans, the cheque treasury, transport income and plan images.
Presentation only: rules are in main/accounting/{instalments,transport,images,contracts}.
"""
from datetime import date

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from main.accounting import contracts, formspec, images, instalments, ledger, transport
from main.accounting.formspec import Field
from main.accounting.parse import jalali_str, parse_int_or_none, parse_jalali
from main.models import DocumentImage, Guarantee, Installment, InstallmentPerson, InstallmentPlan, Party, TransportIncome
from main.office.errors import Invalid, OfficeError
from main.views.accounting_finance import _act, _form_modal, _modal, _reg, _url
from main.views.accounting_panel import _done, _failed, _paged, _today_in
from main.views.accounting_views import _guard

PLAN_STATUS_CHIP = {'active': 'brand', 'settled': 'ok', 'canceled': 'bad'}
POSITION_CHIP = {'office': 'warn', 'treasury': 'brand', 'collected': 'ok', 'bounced': 'bad'}


# ---------- tabs ----------

def tab_plans(request, year, ctx):
    rows = []
    for p in instalments.plans_for(request.user, year).order_by('-number'):
        rows.append({'cells': [p.number, jalali_str(p.date), p.party.name, ('money', p.total_debt), ('money', p.cash_paid),
                               ('money', p.plan_amount), f'{p.paid_count} از {p.count}',
                               (p.get_status_display(), PLAN_STATUS_CHIP[p.status])],
                     'actions': [_act('مشاهده', _url('acc_p_plan_detail', p.id))]})
    _reg(ctx, ['شماره', 'تاریخ', 'مودی', 'کل بدهی', 'پرداخت نقدی', 'مبلغ تقسیط', 'اقساط تسویه‌شده', 'وضعیت'], rows,
         empty='پرونده تقسیطی ثبت نشده است.', icon='calendar-check',
         new_url=None if year.is_closed else _url('acc_p_plan_new', year.id), new_label='پرونده تقسیط جدید')


def tab_received(request, year, ctx):
    position, q = request.GET.get('position', ''), request.GET.get('q', '')
    rows = []
    for i in instalments.received_documents(request.user, year, position=position, q=q):
        actions = {'office': [('ارسال به خزانه', 'treasury', 'paper-plane', '')],
                   'treasury': [('وصول شد', 'collected', 'check', ''), ('برگشت خورد', 'bounced', 'rotate-left', 'bad')],
                   'bounced': [('ارسال مجدد به خزانه', 'treasury', 'paper-plane', '')]}.get(i.position, [])
        rows.append({'cells': [i.get_method_display(), f'{i.series} / {i.serial}'.strip(' /'), i.owner_name or i.plan.party.name,
                               i.bank or '—', jalali_str(i.cheque_date), ('money', i.amount),
                               f'پرونده {i.plan.number}', (i.get_position_display(), POSITION_CHIP[i.position])],
                     'actions': [_act(label, _url('acc_p_cheque_move', i.id, pos), 'post', icon, cls)
                                 for label, pos, icon, cls in actions]
                     + [_act('سابقه', _url('acc_p_cheque_detail', i.id), 'modal', 'clock-rotate-left')]})
    _reg(ctx, ['نوع', 'سری / سریال', 'صاحب حساب', 'بانک', 'تاریخ چک', 'مبلغ (ریال)', 'پرونده', 'موقعیت'], rows,
         empty='چک یا سفته‌ای دریافت نشده است.', icon='money-check',
         filters={'q': 'سریال یا نام', 'select': ('position', 'همه موقعیت‌ها', Installment.POSITIONS)})


def tab_transport(request, year, ctx):
    rows = []
    for t in transport.incomes_for(request.user, year).order_by('-number'):
        rows.append({'cells': [t.number, jalali_str(t.date), t.plate, t.service, t.party.name if t.party else '—',
                               ('money', t.amount), (t.get_status_display(), 'ok' if t.status == 'received' else 'bad')],
                     'actions': [] if t.status != 'received' or year.is_closed else [
                         _act('ابطال', _url('acc_p_transport_cancel', t.id), 'post', 'ban', 'bad', 'این درآمد باطل شود؟')]})
    _reg(ctx, ['شماره', 'تاریخ', 'پلاک', 'نوع خدمت', 'پرداخت‌کننده', 'مبلغ (ریال)', 'وضعیت'], rows,
         empty='درآمد حمل و نقلی ثبت نشده است.', icon='truck',
         new_url=None if year.is_closed else _url('acc_p_transport_new', year.id), new_label='ثبت درآمد حمل و نقل',
         intro={'title': 'جمع درآمد حمل و نقل سال', 'cols': ['مجموع دریافتی (ریال)'], 'empty': '',
                'rows': [[('money', transport.total(request.user, year))]]})


def tab_planimages(request, year, ctx):
    qs = DocumentImage.objects.filter(municipality=ctx['muni'], plan__fiscal_year=year).select_related('plan__party')
    page = _paged(request, qs)
    rows = [{'cells': [i.plan.number, i.plan.party.name, i.title, f'{max(1, (i.size + 1023) // 1024)} کیلوبایت',
                       jalali_str(i.created_at.date())],
             'actions': [_act('نمایش', _url('acc_p_image_file', i.id), 'link', 'eye'),
                         _act('حذف', _url('acc_p_image_delete', i.id), 'post', 'trash', 'bad', 'این تصویر حذف شود؟')]}
            for i in page]
    _reg(ctx, ['پرونده', 'مودی', 'عنوان', 'حجم', 'تاریخ بارگذاری'], rows, empty='تصویری برای پرونده‌ها بارگذاری نشده است.',
         icon='images', new_url=None if year.is_closed else _url('acc_p_planimage_new', year.id),
         new_label='افزودن تصویر پرونده')
    ctx['page'] = page


BUILDERS = {'plans': tab_plans, 'received': tab_received, 'transport': tab_transport, 'planimages': tab_planimages}


# ---------- plans ----------

PLAN_FIELDS = [Field('party', 'مودی', 'fk', model=Party, size=2, label_of=lambda o: f'{o.name} {o.national_id}'.strip()),
               Field('on', 'تاریخ پرونده', 'date', size=1), Field('property_file', 'شماره پرونده', 'text', required=False, size=1, maxlength=40),
               Field('renovation_code', 'کد نوسازی', 'text', required=False, size=1, maxlength=40),
               Field('plot_no', 'پلاک ثبتی', 'text', required=False, size=1, maxlength=40),
               Field('address', 'آدرس', 'text', required=False, size=4, maxlength=500),
               Field('letter_no', 'شماره نامه', 'text', required=False, size=1, maxlength=40),
               Field('letter_date', 'تاریخ نامه', 'date', required=False, size=1),
               Field('request_no', 'شماره درخواست', 'text', required=False, size=2, maxlength=40),
               Field('total_debt', 'کل بدهی (ریال)', 'amount', size=2), Field('cash_paid', 'پرداخت نقدی (ریال)', 'amount', required=False, size=2),
               Field('count', 'تعداد اقساط', 'text', size=1, maxlength=3), Field('first_due', 'موعد اولین قسط', 'date', size=1),
               Field('description', 'توضیحات', 'text', required=False, size=4, maxlength=500)]


@_guard()
def acc_p_plan_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    action = _url('acc_p_plan_new', year.id)
    kw = dict(title='پرونده تقسیط جدید', fields=PLAN_FIELDS, action=action,
              subtitle='مبلغ تقسیط = کل بدهی منهای پرداخت نقدی؛ اقساط ماهانه و مساوی ساخته می‌شود.')
    if request.method != 'POST':
        return _form_modal(request, values={'on': _today_in(year), 'count': '12'}, **kw)
    muni = ledger.municipality_of(request.user)
    try:
        data = formspec.parse(muni, PLAN_FIELDS, request.POST)
        plan = instalments.create_plan(request.user, year, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done(f'پرونده تقسیط شماره {plan.number} با {plan.count} قسط ثبت شد.')


def _plan_modal(request, plan, notice=None, error=None, status=200):
    plan = instalments.get_plan(request.user, plan.pk)
    return _modal(request, 'plan_detail.html', {
        'plan': plan, 'year': plan.fiscal_year, 'c': instalments.counters(plan), 'notice': notice, 'error': error,
        'rows': plan.installments.all(), 'people': plan.people.select_related('party'),
        'guarantees': plan.guarantees.all(), 'images': plan.images.all(), 'editable': plan.status == 'active' and not plan.fiscal_year.is_closed},
        status)


@_guard()
def acc_p_plan_detail(request, plan_id):
    return _plan_modal(request, instalments.get_plan(request.user, plan_id))


@_guard()
@require_POST
def acc_p_plan_cancel(request, plan_id):
    plan = instalments.get_plan(request.user, plan_id)
    try:
        instalments.cancel_plan(request.user, plan, date.today())
    except OfficeError as exc:
        return _plan_modal(request, plan, error=str(exc), status=exc.status)
    return _done('پرونده تقسیط فسخ شد.')


INSTALLMENT_FIELDS = [
    Field('method', 'روش پرداخت', 'select', choices=Installment.METHODS, size=2), Field('on', 'تاریخ پرداخت', 'date', size=1),
    Field('amount', 'مبلغ (ریال)', 'amount', size=1),
    Field('series', 'سری / شناسه صیاد (چک و سفته)', 'text', required=False, size=2, maxlength=40),
    Field('serial', 'سریال (چک و سفته)', 'text', required=False, size=2, maxlength=40),
    Field('bank', 'بانک', 'text', required=False, size=2, maxlength=100),
    Field('account_no', 'شماره حساب', 'text', required=False, size=2, maxlength=40),
    Field('owner_name', 'صاحب حساب', 'text', required=False, size=2, maxlength=150),
    Field('owner_national_id', 'کد ملی صاحب حساب', 'text', required=False, size=1, maxlength=11),
    Field('cheque_date', 'تاریخ چک', 'date', required=False, size=1)]


@_guard()
def acc_p_installment_pay(request, installment_id):
    inst = instalments.get_installment(request.user, installment_id)
    if inst is None:
        raise Http404()
    action, back = _url('acc_p_installment_pay', inst.id), _url('acc_p_plan_detail', inst.plan_id)
    kw = dict(title=f'پرداخت قسط {inst.seq}', fields=INSTALLMENT_FIELDS, action=action,
              subtitle=f'مبلغ قسط {inst.amount:,} ریال، باقی‌مانده {inst.remaining:,} ریال. چک و سفته باید کل باقی‌مانده را پوشش دهد '
                       'و پس از تایید خزانه پرداخت‌شده حساب می‌شود.', extra={'back_url': back})
    if request.method != 'POST':
        return _form_modal(request, values={'on': _today_in(inst.plan.fiscal_year), 'method': 'cash',
                                            'amount': int(inst.remaining)}, **kw)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), INSTALLMENT_FIELDS, request.POST)
        instalments.pay(request.user, inst, data.pop('on'), data.pop('amount'), data.pop('method'), **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _plan_modal(request, inst.plan, notice='پرداخت ثبت شد.')


PERSON_FIELDS = [Field('party', 'شخص', 'fk', model=Party, size=2, label_of=lambda o: f'{o.name} {o.national_id}'.strip()),
                 Field('relation', 'نوع ارتباط', 'select', choices=InstallmentPerson.RELATIONS, size=2)]


@_guard()
def acc_p_plan_person(request, plan_id):
    plan = instalments.get_plan(request.user, plan_id)
    action, back = _url('acc_p_plan_person', plan.id), _url('acc_p_plan_detail', plan.id)
    kw = dict(title='افزودن فرد به پرونده', fields=PERSON_FIELDS, action=action, extra={'back_url': back})
    if request.method != 'POST':
        return _form_modal(request, **kw)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), PERSON_FIELDS, request.POST)
        instalments.add_person(request.user, plan, data['party'], data['relation'])
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _plan_modal(request, plan, notice='فرد افزوده شد.')


PLAN_GUARANTEE_FIELDS = [
    Field('kind', 'نوع ضمانت', 'select', choices=Guarantee.KINDS, size=2),
    Field('doc_kind', 'نوع مدرک', 'select', choices=Guarantee.DOC_KINDS, size=2),
    Field('party', 'صاحب مدرک', 'fk', model=Party, size=2, label_of=lambda o: o.name),
    Field('serial', 'شماره / سریال', 'text', size=2, maxlength=60), Field('bank', 'بانک', 'text', required=False, size=2, maxlength=100),
    Field('date', 'تاریخ مدرک', 'date', size=1), Field('expires_on', 'تاریخ سررسید', 'date', size=1),
    Field('amount', 'مبلغ (ریال)', 'amount', size=2)]


@_guard()
def acc_p_plan_guarantee(request, plan_id):
    plan = instalments.get_plan(request.user, plan_id)
    action, back = _url('acc_p_plan_guarantee', plan.id), _url('acc_p_plan_detail', plan.id)
    kw = dict(title='ثبت ضمانت برای پرونده', fields=PLAN_GUARANTEE_FIELDS, action=action, extra={'back_url': back})
    if request.method != 'POST':
        return _form_modal(request, values={'date': _today_in(plan.fiscal_year), 'kind': 'obligations'}, **kw)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), PLAN_GUARANTEE_FIELDS, request.POST)
        contracts.create_guarantee(request.user, plan=plan, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _plan_modal(request, plan, notice='ضمانت ثبت شد.')


PLAN_IMAGE_FIELDS = [Field('number', 'شماره تقسیط', 'text', size=1, maxlength=10), Field('title', 'عنوان تصویر', 'text', size=3, maxlength=150)]


@_guard()
def acc_p_planimage_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    kw = dict(title='افزودن تصویر پرونده تقسیط', fields=PLAN_IMAGE_FIELDS, action=_url('acc_p_planimage_new', year.id),
              multipart=True, subtitle='فایل PDF یا تصویر (JPG، PNG) تا ۵ مگابایت.', extra={'file_field': True})
    if request.method != 'POST':
        return _form_modal(request, **kw)
    try:
        number = parse_int_or_none(request.POST.get('number'))
        plan = InstallmentPlan.objects.filter(municipality=ledger.municipality_of(request.user), fiscal_year=year,
                                              number=number).first() if number else None
        if plan is None:
            raise Invalid('پرونده‌ای با این شماره تقسیط در این سال مالی نیست.')
        images.upload(request.user, plan, request.FILES.get('file'), request.POST.get('title', ''))
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done('تصویر بارگذاری شد.')


# ---------- received cheques (treasury) ----------

@_guard()
@require_POST
def acc_p_cheque_move(request, installment_id, position):
    inst = instalments.get_installment(request.user, installment_id)
    if inst is None:
        raise Http404()
    try:
        instalments.move_cheque(request.user, inst, position, date.today())
    except OfficeError as exc:
        return _failed(exc)
    return _done('موقعیت چک تغییر کرد.')


@_guard()
def acc_p_cheque_detail(request, installment_id):
    inst = instalments.get_installment(request.user, installment_id)
    if inst is None:
        raise Http404()
    return _modal(request, 'cheque_detail.html', {'i': inst, 'events': inst.events.select_related('user')})


# ---------- transport income ----------

TRANSPORT_FIELDS = [Field('on', 'تاریخ', 'date', size=1), Field('plate', 'پلاک خودرو', 'text', size=1, maxlength=20),
                    Field('service', 'نوع خدمت', 'text', size=2, maxlength=100),
                    Field('party', 'پرداخت‌کننده', 'fk', model=Party, required=False, size=2, label_of=lambda o: o.name),
                    Field('amount', 'مبلغ (ریال)', 'amount', size=2),
                    Field('receipt_no', 'شماره رسید', 'text', required=False, size=2, maxlength=40),
                    Field('description', 'توضیحات', 'text', required=False, size=4, maxlength=300)]


@_guard()
def acc_p_transport_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    kw = dict(title='ثبت درآمد حمل و نقل', fields=TRANSPORT_FIELDS, action=_url('acc_p_transport_new', year.id))
    if request.method != 'POST':
        return _form_modal(request, values={'on': _today_in(year)}, **kw)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), TRANSPORT_FIELDS, request.POST)
        t = transport.record(request.user, year, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done(f'درآمد حمل و نقل شماره {t.number} ثبت شد.')


@_guard()
@require_POST
def acc_p_transport_cancel(request, income_id):
    income = transport.get_income(request.user, income_id)
    try:
        transport.cancel(request.user, income)
    except OfficeError as exc:
        return _failed(exc)
    return _done('درآمد ابطال شد.')
