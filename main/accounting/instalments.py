"""Instalment plans (تقسیط) and the cheques/notes received for them (خزانه / تغییر وضعیت).

Rules:
  * plan amount = total debt - cash paid up front, and must be > 0;
  * the plan amount is split into ``count`` instalments, a month apart from ``first_due`` (Jalali months, last day
    clamped); every instalment is the rounded-down share and the last one takes the remainder, so the schedule always
    sums exactly to the plan amount;
  * cash/transfer/card/online payments count at once and may be partial; a cheque or note must cover the whole
    remaining instalment and only counts as paid when the treasury confirms it was collected;
  * cheque position: office -> treasury -> collected | bounced; a bounced cheque frees the instalment for a new payment;
  * a plan is settled when every instalment is paid; cancelling (فسخ) stops further payments.
"""
from datetime import date

import jdatetime
from django.db import transaction
from django.db.models import Count, F, Q

from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import Installment, InstallmentEvent, InstallmentPerson, InstallmentPlan, Municipality
from main.office.errors import Conflict, Invalid

MAX_COUNT = 60
CHEQUE_METHODS = ('cheque', 'promissory')
POSITION_FLOW = {'office': ('treasury',), 'treasury': ('collected', 'bounced', 'office'), 'bounced': ('treasury', 'office'),
                 'collected': ()}


def add_jalali_months(start, months):
    j = jdatetime.date.fromgregorian(date=start)
    total = j.year * 12 + (j.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last = 31 if month <= 6 else 30 if month <= 11 else (30 if jdatetime.date(year, 1, 1).isleap() else 29)
    return jdatetime.date(year, month, min(j.day, last)).togregorian()


def split(total, count):
    """Equal shares in whole rials; the last share takes the remainder so the parts sum to the total."""
    base = int(total) // count
    parts = [base] * count
    parts[-1] += int(total) - base * count
    return parts


def plans_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return InstallmentPlan.objects.filter(municipality=muni, fiscal_year=year).select_related('party').annotate(
        paid_count=Count('installments', filter=Q(installments__paid_amount=F('installments__amount'))))


def get_plan(actor, plan_id):
    muni = municipality_of(actor)
    return _own(muni, InstallmentPlan.objects.select_related('fiscal_year', 'party').filter(pk=plan_id).first())


def get_installment(actor, installment_id):
    muni = municipality_of(actor)
    inst = Installment.objects.select_related('plan__fiscal_year', 'plan__party').filter(pk=installment_id).first()
    _own(muni, inst.plan if inst else None)
    return inst


def counters(plan):
    rows = list(plan.installments.all())
    paid = sum(1 for i in rows if i.paid_amount >= i.amount)
    return {'registered': len(rows), 'settled': paid, 'remaining': len(rows) - paid,
            'bounced': sum(1 for i in rows if i.position == 'bounced'),
            'paid_total': sum((i.paid_amount for i in rows), 0),
            'left_total': sum((i.amount - i.paid_amount for i in rows), 0)}


def create_plan(actor, year, *, party, total_debt, cash_paid=0, count, first_due, on, property_file='',
                renovation_code='', plot_no='', address='', letter_no='', letter_date=None, request_no='',
                description=''):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    party = _own_or_invalid(muni, party, 'مودی')
    total_debt, cash_paid = _amount(total_debt), _amount(cash_paid)
    if total_debt <= 0:
        raise Invalid('کل بدهی باید بیشتر از صفر باشد.')
    if cash_paid >= total_debt:
        raise Invalid('پرداخت نقدی باید کمتر از کل بدهی باشد؛ مبلغ تقسیط صفر می‌شود.')
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise Invalid('تعداد اقساط نامعتبر است.')
    if not 1 <= count <= MAX_COUNT:
        raise Invalid(f'تعداد اقساط باید بین ۱ و {MAX_COUNT} باشد.')
    if not (year.start_date <= on <= year.end_date):
        raise Invalid('تاریخ باید داخل سال مالی باشد.')
    if first_due < on:
        raise Invalid('موعد اولین قسط قبل از تاریخ پرونده است.')
    plan_amount = total_debt - cash_paid
    if plan_amount < count:
        raise Invalid('مبلغ تقسیط از تعداد اقساط کمتر است.')
    with transaction.atomic():
        _locked(Municipality, muni.id)
        last = InstallmentPlan.objects.filter(municipality=muni, fiscal_year=year).order_by('-number').values_list(
            'number', flat=True).first() or 0
        plan = InstallmentPlan.objects.create(
            municipality=muni, fiscal_year=year, number=last + 1, date=on, party=party, total_debt=total_debt,
            cash_paid=cash_paid, plan_amount=plan_amount, count=count, created_by=actor,
            property_file=_text(property_file, 'شماره پرونده', False)[:40],
            renovation_code=_text(renovation_code, 'کد نوسازی', False)[:40], plot_no=_text(plot_no, 'پلاک', False)[:40],
            address=_text(address, 'آدرس', False), letter_no=_text(letter_no, 'شماره نامه', False)[:40],
            letter_date=letter_date, request_no=_text(request_no, 'شماره درخواست', False)[:40],
            description=_text(description, 'توضیحات', False))
        Installment.objects.bulk_create([
            Installment(plan=plan, seq=i, due_date=add_jalali_months(first_due, i - 1), amount=amount)
            for i, amount in enumerate(split(plan_amount, count), start=1)])
    return plan


def _refresh_status(plan):
    if plan.status == 'canceled':
        return
    left = plan.installments.filter(paid_amount__lt=F('amount')).exists()
    status = 'active' if left else 'settled'
    if plan.status != status:
        plan.status = status
        plan.save(update_fields=['status'])


def cancel_plan(actor, plan, on):
    muni = municipality_of(actor)
    _own(muni, plan)
    with transaction.atomic():
        plan = _locked(InstallmentPlan, plan.pk)
        if plan.status != 'active':
            raise Conflict('فقط پرونده در جریان فسخ می‌شود.')
        if plan.installments.filter(position__in=('office', 'treasury')).exists():
            raise Conflict('چک دریافتی این پرونده هنوز وصل یا برگشت نشده است؛ ابتدا وضعیت آن را مشخص کنید.')
        if on < plan.date:
            raise Invalid('تاریخ فسخ قبل از تاریخ پرونده است.')
        plan.status, plan.canceled_on = 'canceled', on
        plan.save(update_fields=['status', 'canceled_on'])
    return plan


def pay(actor, installment, on, amount, method, *, series='', serial='', bank='', account_no='', owner_name='',
        owner_national_id='', cheque_date=None):
    """Record a payment of one instalment (see the module docstring for cash versus cheque)."""
    muni = municipality_of(actor)
    _own(muni, installment.plan)
    if method not in dict(Installment.METHODS):
        raise Invalid('روش پرداخت نامعتبر است.')
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ باید بیشتر از صفر باشد.')
    with transaction.atomic():
        inst = Installment.objects.select_related('plan__fiscal_year').select_for_update().get(pk=installment.pk)
        plan = _locked(InstallmentPlan, inst.plan_id)
        if plan.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        if plan.status != 'active':
            raise Conflict('پرونده تقسیط در جریان نیست.')
        if inst.position in ('office', 'treasury'):
            raise Conflict('برای این قسط چک دریافت شده و منتظر وصول است.')
        if on < plan.date:
            raise Invalid('تاریخ پرداخت قبل از تاریخ پرونده است.')
        if amount > inst.remaining:
            raise Conflict('مبلغ بیشتر از باقی‌مانده قسط است.')
        if method in CHEQUE_METHODS:
            if amount != inst.remaining:
                raise Invalid('مبلغ چک یا سفته باید برابر باقی‌مانده قسط باشد.')
            serial = _text(serial, 'سریال')[:40]
            owner_national_id = _text(owner_national_id, 'کد ملی صاحب حساب', False)[:11]
            if cheque_date is None:
                raise Invalid('تاریخ چک را وارد کنید.')
            inst.method, inst.series, inst.serial = method, _text(series, 'سری', False)[:40], serial
            inst.bank, inst.account_no = _text(bank, 'بانک', False)[:100], _text(account_no, 'شماره حساب', False)[:40]
            inst.owner_name, inst.owner_national_id = _text(owner_name, 'صاحب حساب', False)[:150], owner_national_id
            inst.cheque_date, inst.position = cheque_date, 'office'
            inst.save()
            InstallmentEvent.objects.create(installment=inst, position='office', date=on, user=actor)
        else:
            inst.paid_amount += amount
            inst.paid_on, inst.method, inst.position = on, method, ''
            inst.save(update_fields=['paid_amount', 'paid_on', 'method', 'position'])
            _refresh_status(plan)
    return inst


def move_cheque(actor, installment, position, on, note=''):
    """Treasury step for a received cheque/note; 'collected' makes the instalment paid, 'bounced' reopens it."""
    muni = municipality_of(actor)
    _own(muni, installment.plan)
    if position not in dict(Installment.POSITIONS):
        raise Invalid('موقعیت نامعتبر است.')
    with transaction.atomic():
        inst = Installment.objects.select_for_update().get(pk=installment.pk)
        plan = _locked(InstallmentPlan, inst.plan_id)
        if not inst.is_cheque or not inst.position:
            raise Conflict('برای این قسط چک یا سفته‌ای ثبت نشده است.')
        if position not in POSITION_FLOW[inst.position]:
            raise Conflict('این تغییر موقعیت مجاز نیست.')
        if on < plan.date:
            raise Invalid('تاریخ قبل از تاریخ پرونده است.')
        inst.position = position
        if position == 'collected':
            inst.paid_amount, inst.paid_on = inst.amount, on
        inst.save(update_fields=['position', 'paid_amount', 'paid_on'])
        InstallmentEvent.objects.create(installment=inst, position=position, date=on, user=actor,
                                        note=_text(note, 'توضیح', False)[:300])
        _refresh_status(plan)
    return inst


def received_documents(actor, year, *, position='', q=''):
    """Cheques and notes received on plans of the year (the treasury list), newest due date first."""
    muni = municipality_of(actor)
    _own(muni, year)
    qs = Installment.objects.filter(plan__municipality=muni, plan__fiscal_year=year, method__in=CHEQUE_METHODS
                                    ).exclude(position='').select_related('plan__party')
    if position in dict(Installment.POSITIONS):
        qs = qs.filter(position=position)
    q = (q or '').strip()
    if q:
        qs = qs.filter(Q(serial__icontains=q) | Q(series__icontains=q) | Q(owner_name__icontains=q)
                       | Q(owner_national_id__icontains=q) | Q(plan__party__name__icontains=q))
    return qs.order_by('due_date', 'id')


def add_person(actor, plan, party, relation):
    muni = municipality_of(actor)
    _own(muni, plan)
    party = _own_or_invalid(muni, party, 'شخص')
    if relation not in dict(InstallmentPerson.RELATIONS):
        raise Invalid('نوع ارتباط نامعتبر است.')
    with transaction.atomic():
        _locked(InstallmentPlan, plan.pk)
        person, created = InstallmentPerson.objects.get_or_create(plan=plan, party=party, relation=relation)
        if not created:
            raise Conflict('این شخص با همین ارتباط قبلاً ثبت شده است.')
    return person
