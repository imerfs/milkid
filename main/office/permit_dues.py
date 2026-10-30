"""Construction without a permit, step 7: the fees and the price of the services (عوارض و بهای خدمات), the payment and the instalments.

- **The sheet** («فرم محاسبه عوارض و بهای خدمات»): the financial officer (or the dehyari) picks the street width and the system fills the areas from the visit
  report (``fee_tables`` holds the rates of the dehyari's workbooks and the calculation); the officer corrects what is wrong and issues the sheet. The owner
  sees the total and prints the sheet (the officer, the dehyari sign it).
- **Payment:** the owner records the bank slips (with the scan); the staff or the officer confirm them.
- **Instalments:** an owner who cannot pay all at once asks for instalments (count, first due date). The administrative expert or the dehyari approve, the
  financial officer signs; the owner then registers the cheques (number, bank, amount, due date) and types the dehyari's legal-entity id (شناسه حقوقی) they were
  written to; the financial officer confirms the registration. With the cheques confirmed the fees count as settled.
- **Ending the step:** when the fees are settled (paid in full or the cheques confirmed) any of the staff or the officer confirms and the file goes on to step 8.
"""
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from main import lifecycle
from main.access import can
from main.accounting.instalments import add_jalali_months, split
from main.accounting.parse import digits, jalali_str, parse_amount, parse_jalali
from main.models import PermitDocument
from main.notifications import notify
from main.office import fee_tables, permit_form, permit_report, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

MAX_RECEIPTS = 6
MAX_CHEQUES = 24
RECEIPT_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png')


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def _now():
    return timezone.localtime().strftime('%Y/%m/%d %H:%M')


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 7 and permit.state == 'done'


def is_officer(user, permit):
    """The village's financial officer (and the dehyari): the sheet, the plan's signature and the cheques."""
    return can(user, 'permit.fees') and permits.files_for(user).filter(pk=permit.pk).exists()


def is_decider(user, permit):
    """The administrative expert and the dehyari decide on an instalment request."""
    return can(user, 'permit.plan') and permits.files_for(user).filter(pk=permit.pk).exists()


def is_staff(user, permit):
    return may_open(user, permit) or is_officer(user, permit)


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    if permit is None:
        from main.models import PermitFile     # pylint: disable=import-outside-toplevel
        found = PermitFile.objects.select_related('request', 'request__user', 'request__user__profile', 'parcel').filter(pk=file_id, track='unlicensed').first()
        if found is not None and can(user, 'permit.fees') and permits.files_for(user).filter(pk=found.pk).exists():
            permit = found
    return permit if permit is not None and permit.unlicensed else None


def _officers(permit):
    village = permit_step2._village(permit)      # pylint: disable=protected-access
    return get_user_model().objects.filter(is_active=True, profile__role='accountant', profile__city_village=village)


def tell_the_officer(permit):
    """The reply was confirmed: the financial officer has the sheet to issue."""
    for officer in _officers(permit):
        notify(officer, 'عوارض ساخت‌وساز بدون پروانه', f'مرحله‌ی جوابیه‌ی کارشناس پرونده {permit.pk} تایید شد؛ عوارض و بهای خدمات را محاسبه کنید.', request=permit.request)


def _staff(permit):
    return permits._staff_to_tell(permit_step2._village(permit))       # pylint: disable=protected-access


# ---------- the sheet ----------

def sheet_inputs(permit, width=None):
    """The inputs of the sheet: the issued ones, else the street width's defaults filled from the visit report."""
    saved = ((permit.dues or {}).get('sheet') or {}).get('inputs')
    if saved and (width is None or width == saved.get('width')):
        return {**fee_tables.defaults(saved['width']), **saved}
    width = width if width in fee_tables.WIDTHS else '8'
    out = fee_tables.defaults(width)
    values = permit_report.data(permit)
    totals = permit_report.totals(values)
    floors = {key: totals['floors'][key]['total'] for key, _ in permit_report.FLOORS}
    f = values['floors']
    num = permit_report._num                                     # pylint: disable=protected-access
    pilotis = num(f['ground'].get('pilotis', ''))
    commercial = {key: num(f[key].get('commercial', '')) for key, _ in permit_report.FLOORS}
    overhang = {key: num(f[key].get('overhang', '')) for key, _ in permit_report.FLOORS}
    res = {key: floors[key] - commercial[key] - overhang[key] for key, _ in permit_report.FLOORS}
    res['ground'] -= pilotis
    upper = res['second'] + res['third']
    out.update({'a_res_0': permit_report._fmt(pilotis), 'a_res_1': permit_report._fmt(res['ground']), 'a_res_2': permit_report._fmt(res['first']),      # pylint: disable=protected-access
                'a_res_3': permit_report._fmt(upper), 'a_res_4': permit_report._fmt(overhang['ground'] + overhang['first']),                          # pylint: disable=protected-access
                'a_res_5': permit_report._fmt(overhang['second'] + overhang['third']),                                                                # pylint: disable=protected-access
                'a_com_1': permit_report._fmt(commercial['ground']), 'a_com_2': permit_report._fmt(commercial['first']),                              # pylint: disable=protected-access
                'a_com_3': permit_report._fmt(commercial['second'] + commercial['third']),                                                            # pylint: disable=protected-access
                'annual': permit_report._fmt(permit.area_m2 or 0)})                                                                                   # pylint: disable=protected-access
    street = sum(Decimal(str((values['limits'][side] or {}).get('existing') or 0)) for side, _ in permit_report.SIDES
                 if (values['limits'][side] or {}).get('adjacent') == 'معبر')
    out['curb_len'] = permit_report._fmt(street)                                       # pylint: disable=protected-access
    return out


def _number(value, label):
    text = digits(value).replace('٫', '.').replace(',', '.').strip()
    if not text:
        return '0'
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise Invalid(f'{label} را به‌صورت عدد وارد کنید.') from None
    if number < 0 or number > 10_000_000_000:
        raise Invalid(f'{label} معتبر نیست.')
    return format(number.normalize(), 'f')


def parse_inputs(post):
    width = post.get('width')
    if width not in fee_tables.WIDTHS:
        raise Invalid('عرض معبر را انتخاب کنید.')
    out = {'width': width}
    for key, label in (('b', 'ضریب شورا (B)'), ('fence', 'طول حصار'), ('join', 'مساحت الحاقی'), ('curb_len', 'طول جدول‌گذاری'),
                       ('prep_w', 'عرض معبر زیرسازی'), ('annual', 'مساحت عوارض سالیانه')):
        out[key] = _number(post.get(key), label)
    for gkey, title, _, _ in fee_tables.GROUPS:
        for i, floor in enumerate(fee_tables.FLOOR_TITLES):
            out[f'a_{gkey}_{i}'] = _number(post.get(f'a_{gkey}_{i}'), f'{title}، {floor}')
    for no in fee_tables.CHANGE_ROWS:
        out[f'chg_{no}'] = _number(post.get(f'chg_{no}'), f'ردیف {no}')
    for no in fee_tables.FIXED_ROWS:
        out[f'fx_{no}'] = str(parse_amount(post.get(f'fx_{no}')))
    return out


def sheet_view(permit):
    """The rows for the page and the print (only the rows that charge something unless ``all``), with the total."""
    sheet = (permit.dues or {}).get('sheet') or {}
    rows, total = fee_tables.compute(sheet_inputs(permit)) if sheet else ([], 0)
    return {'sheet': sheet, 'rows': [r for r in rows if r['amount']], 'total': total}


@transaction.atomic
def issue_sheet(actor, permit, post):
    if not is_officer(actor, permit):
        raise Forbidden('محاسبه‌ی عوارض با مسئول مالی و دهیار است.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی پرداخت عوارض نیست.')
    if (permit.dues or {}).get('payments') or permit.plan_state:
        raise Conflict('پس از ثبت پرداخت یا درخواست تقسیط، فرم عوارض تغییر نمی‌کند.')
    inputs = parse_inputs(post)
    _, total = fee_tables.compute(inputs)
    data = dict(permit.dues or {})
    old = data.get('sheet') or {}
    data['sheet'] = {'inputs': inputs, 'total': total, 'number': _clean(post.get('number'), 40) or old.get('number', ''), 'date': permit_step2.today(),
                     'by': actor.get_full_name() or actor.username, 'at': _now()}
    permit.dues, permit.dues_state = data, 'issued'
    permit.save(update_fields=['dues', 'dues_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'اعلام عوارض و بهای خدمات: {total:,} ریال (مرحله ۷)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'عوارض و بهای خدمات اعلام شد', f'جمع عوارض و بهای خدمات پرونده {permit.pk}: {total:,} ریال. پرداخت کنید یا درخواست تقسیط بدهید.', request=sr)
    return permit


# ---------- the payments ----------

def payments(permit):
    return list((permit.dues or {}).get('payments') or [])


def _open_for_payments(permit):
    if not at_step(permit) or permit.dues_state != 'issued':
        raise Conflict('عوارض هنوز اعلام نشده یا مرحله تمام شده است.')
    if permit.plan_state in ('registered', 'confirmed'):
        raise Conflict('چک‌ها ثبت شده است؛ پرداخت تازه ثبت نمی‌شود.')


@transaction.atomic
def add_payment(actor, permit, post, uploads=()):
    """A bank slip: the owner types it (and attaches the scan) and the staff confirm it; one the staff record is confirmed at once."""
    mine = permit.request.user_id == actor.id
    if not (mine or is_staff(actor, permit)):
        raise Forbidden('اجازه‌ی ثبت پرداخت را ندارید.')
    _open_for_payments(permit)
    amount = parse_amount(post.get('amount'))
    if not amount:
        raise Invalid('مبلغ پرداخت را وارد کنید.')
    try:
        paid_on = parse_jalali(post.get('date', ''))
    except Invalid as exc:
        raise Invalid('تاریخ فیش را شمسی وارد کنید، مثل ۱۴۰۵/۰۷/۲۶.') from exc
    number = _clean(digits(post.get('slip_no')), 40)
    if not number:
        raise Invalid('شماره‌ی فیش (یا شماره‌ی پیگیری) را وارد کنید.')
    uploads = list(uploads)[:MAX_RECEIPTS]
    for upload in uploads:
        error = permit_form._file_error(upload, RECEIPT_EXTENSIONS, 10 * 1024 * 1024)       # pylint: disable=protected-access
        if error:
            raise Invalid(error)
    data = dict(permit.dues or {})
    rows = list(data.get('payments') or [])
    if any(p['slip_no'] == number for p in rows):
        raise Conflict('این شماره‌ی فیش قبلا ثبت شده است.')
    docs = [PermitDocument.objects.create(file=permit, kind='fee_receipt', document=u, original_name=u.name[:200], size=u.size, uploaded_by=actor).pk for u in uploads]
    rows.append({'id': max([p['id'] for p in rows] + [0]) + 1, 'slip_no': number, 'date': jalali_str(paid_on), 'amount': amount, 'note': _clean(post.get('note')),
                 'docs': docs, 'ok': not mine, 'by': actor.get_full_name() or actor.username, 'at': _now()})
    data['payments'] = rows
    permit.dues = data
    permit.save(update_fields=['dues', 'updated_at'])
    if mine:
        for staff in list(_staff(permit)) + list(_officers(permit)):
            notify(staff, 'فیش پرداخت عوارض', f'متقاضی پرونده {permit.pk} فیش پرداخت را ثبت کرد؛ بررسی و تایید کنید.', request=permit.request)
    return permit


@transaction.atomic
def confirm_payment(actor, permit, payment_id):
    if not is_staff(actor, permit):
        raise Forbidden('تایید پرداخت با کارکنان دهیاری و مسئول مالی است.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی پرداخت عوارض نیست.')
    data = dict(permit.dues or {})
    rows = list(data.get('payments') or [])
    row = next((p for p in rows if p['id'] == payment_id), None)
    if row is None:
        raise Conflict('پرداخت پیدا نشد.')
    row['ok'], row['confirmed_by'] = True, actor.get_full_name() or actor.username
    data['payments'] = rows
    permit.dues = data
    permit.save(update_fields=['dues', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'تایید فیش پرداخت {row["slip_no"]} به مبلغ {row["amount"]:,} ریال (مرحله ۷)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    return permit


@transaction.atomic
def remove_payment(actor, permit, payment_id):
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی پرداخت عوارض نیست.')
    if permit.plan_state in ('registered', 'confirmed'):
        raise Conflict('چک‌ها ثبت شده است.')
    data = dict(permit.dues or {})
    rows = list(data.get('payments') or [])
    row = next((p for p in rows if p['id'] == payment_id), None)
    if row is None:
        raise Conflict('پرداخت پیدا نشد.')
    if not (is_staff(actor, permit) or (permit.request.user_id == actor.id and not row.get('ok'))):
        raise Forbidden('اجازه‌ی حذف این پرداخت را ندارید.')
    for doc in permit.documents.filter(pk__in=row.get('docs') or [], kind='fee_receipt'):
        doc.document.delete(save=False)
        doc.delete()
    data['payments'] = [p for p in rows if p['id'] != payment_id]
    permit.dues = data
    permit.save(update_fields=['dues', 'updated_at'])
    return permit


# ---------- the instalments ----------

def remaining(permit):
    return max(permit.dues_total - permit.dues_paid, 0)


def plan(permit):
    return dict((permit.dues or {}).get('plan') or {})


def schedule(permit):
    """The cheques the plan asks for: equal shares of what is still owed, a Jalali month apart from the first due date."""
    data = plan(permit)
    count, first = int(data.get('count') or 0), data.get('first_due') or ''
    if not count or not first:
        return []
    start = parse_jalali(first)
    return [{'n': i + 1, 'amount': amount, 'due': jalali_str(add_jalali_months(start, i))} for i, amount in enumerate(split(remaining(permit), count))]


@transaction.atomic
def request_plan(user, permit, post):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit) or permit.dues_state != 'issued':
        raise Conflict('عوارض هنوز اعلام نشده است.')
    if permit.plan_state not in ('', 'returned'):
        raise Conflict('درخواست تقسیط قبلاً ثبت شده است.')
    if not remaining(permit):
        raise Conflict('عوارض کامل پرداخت شده است.')
    try:
        count = int(digits(post.get('count')))
    except ValueError:
        raise Invalid('تعداد اقساط را وارد کنید.') from None
    if not 2 <= count <= MAX_CHEQUES:
        raise Invalid(f'تعداد اقساط باید بین ۲ و {MAX_CHEQUES} باشد.')
    try:
        first = parse_jalali(post.get('first_due', ''))
    except Invalid as exc:
        raise Invalid('تاریخ سررسید اولین چک را شمسی وارد کنید، مثل ۱۴۰۵/۰۸/۲۵.') from exc
    if first < timezone.localdate():
        raise Invalid('تاریخ سررسید اولین چک نمی‌تواند گذشته باشد.')
    data = dict(permit.dues or {})
    data['plan'] = {'count': count, 'first_due': jalali_str(first), 'reason': _clean(post.get('reason'), 300), 'at': _now()}
    permit.dues, permit.plan_state = data, 'requested'
    permit.save(update_fields=['dues', 'plan_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'درخواست تقسیط عوارض در {count} قسط (مرحله ۷)', from_user=user, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'درخواست تقسیط عوارض', f'متقاضی پرونده {permit.pk} درخواست تقسیط عوارض داد؛ منتظر تایید کارشناس اداری یا دهیار است.', request=sr)
    return permit


@transaction.atomic
def approve_plan(actor, permit, post):
    if not is_decider(actor, permit):
        raise Forbidden('تایید تقسیط با کارشناس اداری و دهیار است.')
    if not at_step(permit) or permit.plan_state != 'requested':
        raise Conflict('درخواست تقسیطی برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «درخواست تقسیط را بررسی و تایید می‌کنم» لازم است.')
    data = dict(permit.dues or {})
    plan_ = dict(data.get('plan') or {})
    if post.get('count'):
        try:
            count = int(digits(post.get('count')))
        except ValueError:
            raise Invalid('تعداد اقساط را به عدد وارد کنید.') from None
        if not 2 <= count <= MAX_CHEQUES:
            raise Invalid(f'تعداد اقساط باید بین ۲ و {MAX_CHEQUES} باشد.')
        plan_['count'] = count
    plan_['approved'] = {'by': actor.get_full_name() or actor.username, 'at': _now()}
    data['plan'] = plan_
    permit.dues, permit.plan_state = data, 'approved'
    permit.save(update_fields=['dues', 'plan_state', 'updated_at'])
    for officer in _officers(permit):
        notify(officer, 'تقسیط عوارض منتظر امضا', f'تقسیط عوارض پرونده {permit.pk} تایید شد؛ منتظر امضای مسئول مالی است.', request=permit.request)
    return permit


@transaction.atomic
def return_plan(actor, permit, notes):
    """The administrative expert or the dehyari refuse the request; the financial officer may refuse what was approved."""
    allowed = (permit.plan_state == 'requested' and is_decider(actor, permit)) or (permit.plan_state == 'approved' and is_officer(actor, permit))
    if not allowed or not at_step(permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید چرا تقسیط برگشت داده می‌شود.')
    lifecycle.request_documents(permit.request, actor, f'درخواست تقسیط: {notes}')
    permit.plan_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['plan_state', 'staff_notes', 'updated_at'])
    return permit


@transaction.atomic
def sign_plan(actor, permit, post):
    if not is_officer(actor, permit):
        raise Forbidden('امضای تقسیط با مسئول مالی است.')
    if not at_step(permit) or permit.plan_state != 'approved':
        raise Conflict('تقسیط تاییدشده‌ای برای امضا نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «برنامه‌ی اقساط را بررسی و امضا می‌کنم» لازم است.')
    data = dict(permit.dues or {})
    plan_ = dict(data.get('plan') or {})
    plan_['signed'] = {'by': actor.get_full_name() or actor.username, 'at': _now()}
    data['plan'] = plan_
    permit.dues, permit.plan_state = data, 'signed'
    permit.save(update_fields=['dues', 'plan_state', 'updated_at'])
    notify(permit.request.user, 'تقسیط عوارض تایید شد', f'تقسیط عوارض پرونده {permit.pk} تایید و امضا شد؛ چک‌ها را در سامانه ثبت کنید.', request=permit.request)
    return permit


# ---------- the cheques ----------

def cheque_rows(permit):
    """The rows of the registration form: the owner's own entries, else the schedule (amount and due date) with empty number and bank."""
    saved = list(plan(permit).get('cheques') or [])
    if saved:
        return saved
    return [{'n': s['n'], 'no': '', 'bank': '', 'amount': s['amount'], 'due': s['due']} for s in schedule(permit)]


@transaction.atomic
def register_cheques(user, permit, post):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit) or permit.plan_state != 'signed':
        raise Conflict('تقسیط هنوز امضا نشده یا چک‌ها ثبت شده است.')
    legal = digits(post.get('legal_id', ''))
    if not (legal.isdigit() and len(legal) == 11):
        raise Invalid('شناسه‌ی حقوقی دهیاری باید ۱۱ رقم باشد.')
    count = int(plan(permit)['count'])
    rows, last = [], None
    for i in range(count):
        number = digits(post.get(f'c{i}_no', ''))
        bank = _clean(post.get(f'c{i}_bank'), 60)
        amount = parse_amount(post.get(f'c{i}_amount'))
        try:
            due = parse_jalali(post.get(f'c{i}_due', ''))
        except Invalid as exc:
            raise Invalid(f'تاریخ سررسید چک {i + 1} را شمسی وارد کنید.') from exc
        if not number.isdigit() or len(number) > 20 or not bank or not amount:
            raise Invalid(f'شماره، بانک و مبلغ چک {i + 1} را وارد کنید.')
        if last is not None and due <= last:
            raise Invalid('سررسید چک‌ها باید به ترتیب باشد.')
        if due < timezone.localdate():
            raise Invalid(f'سررسید چک {i + 1} نمی‌تواند گذشته باشد.')
        last = due
        rows.append({'n': i + 1, 'no': number, 'bank': bank, 'amount': amount, 'due': jalali_str(due)})
    if len({r['no'] for r in rows}) != len(rows):
        raise Invalid('شماره‌ی چک‌ها نباید تکراری باشد.')
    if sum(r['amount'] for r in rows) != remaining(permit):
        raise Invalid(f'جمع چک‌ها باید برابر باقی‌مانده‌ی عوارض ({remaining(permit):,} ریال) باشد.')
    data = dict(permit.dues or {})
    plan_ = dict(data.get('plan') or {})
    plan_.update({'cheques': rows, 'legal_id': legal, 'registered_at': _now()})
    data['plan'] = plan_
    permit.dues, permit.plan_state = data, 'registered'
    permit.save(update_fields=['dues', 'plan_state', 'updated_at'])
    for officer in _officers(permit):
        notify(officer, 'ثبت چک‌های عوارض', f'متقاضی پرونده {permit.pk} چک‌ها را ثبت کرد؛ ثبت را تایید کنید.', request=permit.request)
    return permit


@transaction.atomic
def confirm_cheques(actor, permit, post):
    if not is_officer(actor, permit):
        raise Forbidden('تایید ثبت چک با مسئول مالی است.')
    if not at_step(permit) or permit.plan_state != 'registered':
        raise Conflict('چکی برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «ثبت چک‌ها را با چک‌های دریافتی و شناسه‌ی حقوقی مطابقت دادم» لازم است.')
    data = dict(permit.dues or {})
    plan_ = dict(data.get('plan') or {})
    plan_['cheques_checked'] = {'by': actor.get_full_name() or actor.username, 'at': _now()}
    data['plan'] = plan_
    permit.dues, permit.plan_state = data, 'confirmed'
    permit.save(update_fields=['dues', 'plan_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='تایید ثبت چک‌های اقساط عوارض (مرحله ۷)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'ثبت چک‌ها تایید شد', f'ثبت چک‌های اقساط پرونده {permit.pk} تایید شد.', request=sr)
    for staff in _staff(permit):
        notify(staff, 'عوارض تسویه شد', f'عوارض پرونده {permit.pk} تسویه شد؛ مرحله را تایید کنید.', request=sr)
    return permit


@transaction.atomic
def return_cheques(actor, permit, notes):
    if not is_officer(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit) or permit.plan_state != 'registered':
        raise Conflict('چکی برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل ثبت چک‌ها چیست.')
    lifecycle.request_documents(permit.request, actor, f'ثبت چک‌ها: {notes}')
    data = dict(permit.dues or {})
    plan_ = dict(data.get('plan') or {})
    plan_['note'] = notes[:300]
    data['plan'] = plan_
    permit.dues, permit.plan_state, permit.staff_notes = data, 'signed', notes[:2000]
    permit.save(update_fields=['dues', 'plan_state', 'staff_notes', 'updated_at'])
    return permit


# ---------- the end of the step ----------

def blocking(permit):
    if permit.dues_state != 'issued':
        return ['عوارض هنوز محاسبه و اعلام نشده است.']
    if not permit.dues_settled:
        return [f'هنوز {remaining(permit):,} ریال از عوارض پرداخت یا با چک تضمین نشده است.']
    return []


@transaction.atomic
def finish(actor, permit, post):
    if not is_staff(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی پرداخت عوارض نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «پرداخت‌ها و چک‌ها را بررسی کردم» لازم است.')
    permit.stage_no = 8
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۷ (پرداخت عوارض و بهای خدمات)', from_user=actor, to_role='citizen', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'مرحله‌ی ۷ تایید شد', f'عوارض پرونده {permit.pk} تسویه و مرحله‌ی ۷ تایید شد؛ پرونده به مرحله‌ی ۸ رفت.', request=sr)
    return permit

