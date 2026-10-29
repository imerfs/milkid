"""Building-permit file, step 1: the application page, the file page and the staff's decisions on it.

The application page is the owner's «ایجاد پرونده اولیه» form (main/templates/main/services/building-permits/step1.html).
The file page is shared by the applicant and the village staff; it is also what the panels open in their drawer.
"""
import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_POST

from main import lifecycle
from main.access import policy_required, role_of
from main.models import PermitDocument, PermitFile, PermitPerson
from main.office import permit_commission, permit_defence, permit_notice, permit_sketch, permit_form, permit_step2, permit_step3, permit_step4, permit_step5, permit_extension, permit_step6, permit_step7, permit_endwork, permit_services, permit_supervision, permits
from main.access import can
from main.office.errors import OfficeError
from main.roles import CITIZEN_ROLES

INLINE_TYPES = {'.pdf', '.jpg', '.jpeg', '.png'}
PERSON_LABELS = (('name', 'نام و نام خانوادگی'), ('father', 'فرزند'), ('grade', 'پایه‌ی پروانه‌ی اشتغال'), ('field', 'رشته'), ('license', 'شماره‌ی پروانه / عضویت'))
DEFENCE_FIELDS = (('name', 'نام و نام خانوادگی'), ('father', 'نام پدر'), ('phone', 'شماره تلفن'), ('village', 'روستا'), ('district', 'بخش'),
                  ('county', 'شهرستان'), ('area', 'متراژ بنای غیرمجاز (متر مربع)'), ('date', 'تاریخ فرم'), ('dehyari', 'نام دهیار (جعبه‌ی تاییدیه)'))
COMMISSION_FIELDS = (('name', 'نام و نام خانوادگی'), ('father', 'نام پدر'), ('id_number', 'شماره شناسنامه'), ('national_id', 'کد ملی'),
                     ('street', 'خیابان / آدرس'), ('phone', 'شماره تماس'), ('date', 'تاریخ فرم'))
FORM_LABELS = (('f04', 'فرم ۰۴ (دستور تهیه‌ی نقشه)'), ('f05', 'فرم ۰۵ (تعهد معماری)'), ('f06', 'فرم ۰۶ (تعهد سازه)'), ('f07', 'فرم ۰۷ (تعهد نظارت)'))
SIDE_LABELS = (('length', 'طول موجود'), ('after', 'ابعاد پس از اصلاح'), ('passage', 'عرض گذر موجود'), ('approved', 'عرض گذر مصوب'))


def _file_url(permit, embed=False):
    return reverse('main:permit_file', args=[permit.pk]) + ('?embed=1' if embed else '')


def _co_rows(values, errors):
    """The optional «other owners» blocks of the form, each with its own values and errors."""
    rows = []
    for n in range(1, permit_form.CO_OWNERS + 1):
        prefix = f'co{n}_'
        row = {'n': n, 'p': prefix, 'national_card': prefix + 'national_card', 'birth_cert': prefix + 'birth_cert',
               'v': {k[len(prefix):]: v for k, v in values.items() if k.startswith(prefix)},
               'e': {k[len(prefix):]: v for k, v in errors.items() if k.startswith(prefix)}}
        row['filled'] = any(row['v'].get(k) for k in ('first_name', 'last_name', 'national_id')) or bool(row['e'])
        rows.append(row)
    return rows


def _application(request, track):
    """Step 1: the applicant fills in the file (owner, property, ownership paper, identity papers, shamim file)."""
    unlicensed = track == 'unlicensed'
    if role_of(request.user) not in CITIZEN_ROLES:
        messages.error(request, 'درخواست ساخت‌وساز بدون پروانه را شهروند ثبت می‌کند.' if unlicensed else 'درخواست پروانه ساختمان را شهروند ثبت می‌کند.')
        return redirect('main:dashboard')
    values, errors = permits.prefill(request.user), {}
    if request.method == 'POST':
        data, errors = permit_form.parse(request.POST, request.FILES, track)
        if not errors:
            try:
                permit = permits.submit(request.user, data)
            except lifecycle.TransitionError as exc:        # the plot is locked: lifecycle words the refusal
                errors = {'renewal_code': str(exc)}
            else:
                messages.success(request, ('پرونده‌ی ساخت‌وساز بدون پروانه ثبت شد؛ کارشناس مدارک را بررسی و مرحله‌ی ۱ را تایید می‌کند.' if unlicensed
                                           else 'پرونده‌ی پروانه ساختمان ثبت شد؛ کارشناس مدارک را بررسی و پرونده را افتتاح می‌کند.'))
                return redirect(_file_url(permit, embed=bool(request.GET.get('embed'))))
        values = permit_form.keep_for_redisplay(request.POST)
    return render(request, 'main/services/building-permits/step1.html', {
        'v': values, 'errors': errors, 'profile': request.user.profile, 'co_rows': _co_rows(values, errors),
        'land_uses': PermitFile.LAND_USES, 'kinds': PermitFile.KINDS, 'unlicensed': unlicensed,
        'co_roles': [(r, label) for r, label in PermitPerson.ROLES if r != 'applicant'],
    }, status=400 if errors else 200)


@login_required
def building_permit_form(request):
    return _application(request, 'permit')


@login_required
def without_permit_form(request):
    return _application(request, 'unlicensed')


@login_required
def permit_file(request, file_id):
    permit = permits.find(request.user, file_id, any_track=True)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    mine = permit.request.user_id == request.user.id
    can_decide = permits.may_open(request.user, permit)
    people = list(permit.people.prefetch_related('documents'))
    return render(request, 'main/permits/detail.html', {
        'permit': permit, 'sr': permit.request, 'people': people, 'tracker': permits.tracker(permit),
        'file_documents': permit.documents.filter(person__isnull=True), 'mine': mine, 'can_decide': can_decide,
        'staff_view': not mine, 'embed': bool(request.GET.get('embed')),
        'supervisor_view': permit.supervisor_id == request.user.id and not mine and not can_decide,
        'suggestions': permits.suggestions(permit) if can_decide else [],
        'history': list(reversed(permit.request.workflow_history or [])),
        'other_requests': permits.applicant_history(permit) if can_decide else [],
        'doc_kinds': PermitDocument.KINDS, 'details': permit.details or {},
        'b': permit.bonyad or {}, 'answer_docs': permit.documents.filter(kind='bonyad_answer'),
        'checks': permit_step3.checks(permit) if permit.stage_no == 3 and permit.bonyad_state == 'uploaded' and can_decide else [],
    })


@login_required
def permit_document(request, doc_id):
    """An identity paper or the shamim file: only its owner and the village's staff, never through /media/."""
    doc = PermitDocument.objects.select_related('file').filter(pk=doc_id).first()
    if doc is None or (permits.find(request.user, doc.file_id, any_track=True) is None
                       and not (doc.kind == 'fee_receipt' and permit_step5.find(request.user, doc.file_id))):
        raise Http404('مدرک پیدا نشد.')
    ext = os.path.splitext(doc.original_name)[1].lower()
    inline = ext in INLINE_TYPES and not request.GET.get('download')
    try:
        response = FileResponse(doc.document.open('rb'), as_attachment=not inline, filename=doc.original_name,
                                content_type=mimetypes.guess_type(doc.original_name)[0] or 'application/octet-stream')
    except OSError as exc:
        raise Http404('فایل پیدا نشد.') from exc
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


def _decide(request, file_id, action):
    permit = permits.find(request.user, file_id, any_track=True)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.POST.get('embed'))
    try:
        action(permit)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(_file_url(permit, embed))


@policy_required('permit.open')
@require_POST
def permit_open(request, file_id):
    def act(permit):
        permits.open_file(request.user, permit, code=request.POST.get('renewal_code', ''),
                          parcel_id=request.POST.get('parcel_id'), notes=request.POST.get('notes', ''))
        messages.success(request, 'پرونده افتتاح شد و به مرحله‌ی ۲ رفت.')
    return _decide(request, file_id, act)


@policy_required('permit.open')
@require_POST
def permit_send_back(request, file_id):
    def act(permit):
        permits.send_back(request.user, permit, request.POST.get('notes', ''))
        messages.success(request, 'پرونده برای رفع نقص به متقاضی برگشت داده شد.')
    return _decide(request, file_id, act)


@policy_required('permit.open')
@require_POST
def permit_refuse(request, file_id):
    def act(permit):
        permits.refuse(request.user, permit, request.POST.get('notes', ''))
        messages.success(request, 'پرونده رد شد.')
    return _decide(request, file_id, act)


@login_required
@require_POST
def permit_supplement(request, file_id):
    permit = permits.find(request.user, file_id, any_track=True)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    kind = request.POST.get('kind', '')
    try:
        permits.supplement(request.user, permit, kind, request.FILES.getlist('document'))
        messages.success(request, 'مدارک فرستاده شد و پرونده دوباره بررسی می‌شود.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return redirect(_file_url(permit, bool(request.POST.get('embed'))))


@login_required
def permit_forms(request, file_id):
    """Step 2: form 1 (the staff fill it), form 2 (the owner fills it), the plot map; each is drawn over the blank form."""
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    if permit.stage_no < 2:
        messages.error(request, 'فرم‌ها پس از افتتاح پرونده در دسترس‌اند.')
        return redirect(_file_url(permit, bool(request.GET.get('embed'))))
    mine = permit.request.user_id == request.user.id
    open_stage = permit.stage_no == 2 and not permit.delivered_at
    staff = permits.may_open(request.user, permit)
    payload = permit_step2.payload(permit)
    return render(request, 'main/permits/forms.html', {
        'permit': permit, 'payload': payload, 'f1': payload['form1'], 'f2': payload['form2'], 'embed': bool(request.GET.get('embed')),
        'can_form1': staff and open_stage, 'can_form2': mine and open_stage, 'can_deliver': staff and open_stage,
        'sides': [(k, label) for k, label in (('north', 'شمالاً'), ('south', 'جنوباً'), ('west', 'غرباً'), ('east', 'شرقاً'))],
        'purposes': permit_step2.PURPOSES.items(),
    })


def _step2_action(request, file_id, action, ok, page='permit_forms'):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    target = reverse(f'main:{page}', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else '')
    return redirect(target)


@login_required
@require_POST
def permit_form1_save(request, file_id):
    return _step2_action(request, file_id, lambda p: permit_step2.save_form1(request.user, p, request.POST), 'فرم ۱ ذخیره شد.')


@login_required
@require_POST
def permit_form2_save(request, file_id):
    return _step2_action(request, file_id, lambda p: permit_step2.save_form2(request.user, p, request.POST), 'فرم ۲ ذخیره شد.')


@login_required
@require_POST
def permit_deliver(request, file_id):
    return _step2_action(request, file_id, lambda p: permit_step2.deliver(request.user, p), 'فرم‌ها تحویل شد و پرونده به مرحله‌ی ۳ رفت.')


@policy_required('permit.open')
@require_POST
def permit_shamim(request, file_id):
    permit = permits.find(request.user, file_id, any_track=True)
    if permit is None or not permits.may_open(request.user, permit):
        raise Http404('پرونده پیدا نشد.')
    info = permit_step2.refresh_shamim(permit)
    messages.success(request, 'فایل شمیم دوباره بررسی شد.' if info.get('ok') else 'فایل شمیم خوانده نشد: ' + ' '.join(info.get('notes', [])))
    return redirect(_file_url(permit, bool(request.POST.get('embed'))))


@login_required
@require_POST
def permit_answer(request, file_id):
    """Step 3: the owner uploads the Bonyad's answer."""
    return _step2_action(request, file_id, lambda p: permit_step3.submit_answer(request.user, p, request.POST, request.FILES),
                         'پاسخ بنیاد فرستاده شد؛ دهیاری صحت آن را بررسی می‌کند.', page='permit_file')


@login_required
@require_POST
def permit_answer_verify(request, file_id):
    return _step2_action(request, file_id, lambda p: permit_step3.verify(request.user, p, request.POST),
                         'صحت پاسخ بنیاد تایید شد.', page='permit_file')


@login_required
@require_POST
def permit_answer_return(request, file_id):
    return _step2_action(request, file_id, lambda p: permit_step3.send_back(request.user, p, request.POST.get('notes', '')),
                         'پاسخ برای اصلاح به متقاضی برگشت داده شد.', page='permit_file')


@login_required
def permit_design(request, file_id):
    """Step 4: engineers, forms 04-07, plan upload, review and the dehyari's signature, all on one page."""
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    if permit.stage_no < 4:
        messages.error(request, 'این بخش پس از تایید پاسخ بنیاد در دسترس است.')
        return redirect(_file_url(permit, bool(request.GET.get('embed'))))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    data = permit_step4.payload(permit)
    open_for_owner = mine and permit.stage_no == 4 and permit.design_state in permit_step4.OPEN_STATES
    docs = {kind: list(permit.documents.filter(kind=kind)) for kind in permit_step4.PLAN_KINDS}
    return render(request, 'main/permits/design.html', {
        'permit': permit, 'd': data, 'embed': bool(request.GET.get('embed')), 'mine': mine, 'staff': staff,
        'can_sign': staff and can(request.user, 'permit.sign') and permit.stage_no == 4 and permit.design_state in ('submitted', 'reviewed'),
        'can_review': staff and permit.stage_no == 4 and permit.design_state == 'submitted',
        'can_return': staff and permit.stage_no == 4 and permit.design_state in ('submitted', 'reviewed'),
        'can_staff_edit': staff and permit.stage_no == 4 and permit.design_state != 'signed',
        'owner_open': open_for_owner, 'people_editable': open_for_owner or (staff and permit.design_state != 'signed' and permit.stage_no == 4),
        'plan_docs': docs, 'plan_kinds': permit_step4.PLAN_KINDS.items(), 'counts': permit_step4.counts(permit),
        'people_rows': [(role, label, [(key, text, data['people'][role].get(key, '')) for key, text in PERSON_LABELS])
                        for role, label in permit_step4.ROLES.items()],
        'form_rows': [(key, label, data['forms'][key]['number'], data['forms'][key]['date']) for key, label in FORM_LABELS],
        'side_rows': [(side, label, [(key, text, data['order']['sides'][side].get(key, '')) for key, text in SIDE_LABELS])
                      for side, label in (('north', 'شمال'), ('south', 'جنوب'), ('east', 'شرق'), ('west', 'غرب'))],
        'tampered': permit_step4.tampered(permit), 'payload': {**data, 'blank': {
            'f04': static('forms/permit/form04_blank.jpg'), 'f07': static('forms/permit/form07_blank.jpg'),
            'letter': static('forms/permit/letterhead.jpg')}, 'file': permit.pk, 'owner': permit.people.first().full_name},
    })


def _design_action(request, file_id, action, ok):
    return _step2_action(request, file_id, action, ok, page='permit_design')


@login_required
@require_POST
def permit_design_people(request, file_id):
    return _design_action(request, file_id, lambda p: permit_step4.save_people(request.user, p, request.POST), 'مشخصات مهندسان ذخیره شد.')


@login_required
@require_POST
def permit_design_forms(request, file_id):
    return _design_action(request, file_id, lambda p: permit_step4.save_forms(request.user, p, request.POST), 'اطلاعات فرم‌ها ذخیره شد.')


@login_required
@require_POST
def permit_design_upload(request, file_id):
    def act(p):
        count = permit_step4.upload_plans(request.user, p, request.POST.get('kind', ''), request.FILES.getlist('plans'))
        messages.info(request, f'{count} فایل نقشه بارگذاری شد.')
    return _design_action(request, file_id, act, 'نقشه‌ها بارگذاری شد.')


@login_required
@require_POST
def permit_design_delete(request, file_id, doc_id):
    return _design_action(request, file_id, lambda p: permit_step4.delete_plan(request.user, p, doc_id), 'نقشه حذف شد.')


@login_required
@require_POST
def permit_design_submit(request, file_id):
    return _design_action(request, file_id, lambda p: permit_step4.submit(request.user, p), 'نقشه‌ها برای بررسی فرستاده شد.')


@login_required
@require_POST
def permit_design_return(request, file_id):
    return _design_action(request, file_id, lambda p: permit_step4.send_back(request.user, p, request.POST.get('notes', '')), 'نقشه‌ها برای اصلاح برگشت داده شد.')


@login_required
@require_POST
def permit_design_review(request, file_id):
    return _design_action(request, file_id, lambda p: permit_step4.review(request.user, p, request.POST), 'نقشه‌ها بررسی شد و منتظر امضای دهیار است.')


@login_required
@require_POST
def permit_design_sign(request, file_id):
    return _design_action(request, file_id, lambda p: permit_step4.sign(request.user, p, request.POST), 'نقشه‌ها امضا شد و پرونده به مرحله‌ی ۵ رفت.')


# ---------- steps 5 and 6: the fees, the payments and the introduction letter ----------

@login_required
def permit_fees(request, file_id):
    """Step 5 (the fee rows, the owner's answer) and step 6 (the payments and the Social Security letter) on one page."""
    permit = permit_step5.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.stage_no < 5:
        messages.error(request, 'عوارض پس از امضای نقشه‌ها توسط دهیار تعیین می‌شود.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    officer = permit_step5.can_define(request.user) and permits.files_for(request.user).filter(pk=permit.pk).exists()
    fees = permit.fees or {}
    editing = officer and permit.stage_no == 5 and permit.fees_state in permit_step5.OBJECTION_STATES
    rows = permit_step5.fee_rows(permit)
    pays = [{**p, 'docs': list(permit.documents.filter(pk__in=p.get('docs') or [], kind='fee_receipt'))} for p in permit_step5.payments(permit)]
    letter = permit_step5.letter_defaults(permit)
    paid = permit_step5.paid_total(permit)
    return render(request, 'main/permits/fees.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'staff': staff, 'officer': officer, 'editing': editing, 'fees': fees,
        'groups': _group_rows(rows), 'chosen': [r for r in rows if r['on']], 'extras': permit_step5.extras(permit),
        'extra_chosen': fees.get('extra') or [], 'payments': pays, 'paid': paid, 'remaining': max((fees.get('total') or 0) - paid, 0),
        'can_answer': mine and permit.stage_no == 5 and permit.fees_state == 'offered',
        'can_pay': (mine or staff or officer) and permit.stage_no == 6 and not permit.insurance_state,
        'can_confirm': (staff or officer) and permit.stage_no == 6 and not permit.insurance_state,
        'can_issue': staff and permit.stage_no == 6 and not permit.insurance_state and permit.paid_up,
        'letter': letter, 'letter_saved': (permit.insurance or {}).get('letter') or {},
        'show_letter': permit.stage_no >= 6 and ((staff and permit.paid_up) or permit.insurance_state),
        'cert': {**permit_step6.defaults(permit), **((permit.insurance or {}).get('cert') or {})},
        'cert_docs': permit.documents.filter(kind='insurance_cert'), 'cert_checks': permit_step6.checks(permit) if staff and permit.insurance_state == 'uploaded' else [],
        'can_cert': mine and permit.stage_no == 6 and permit.insurance_state in permit_step6.OPEN_STATES,
        'can_cert_verify': staff and permit.stage_no == 6 and permit.insurance_state == 'uploaded',
        'payload': {'letter': letter, 'file': permit.pk, 'blank': {'letter': static('forms/permit/letterhead.jpg')}},
    })


def _group_rows(rows):
    groups = []
    for row in rows:
        if not groups or groups[-1]['name'] != row['group']:
            groups.append({'name': row['group'], 'rows': []})
        groups[-1]['rows'].append(row)
    return groups


def _fees_action(request, file_id, action, ok):
    permit = permit_step5.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_fees', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_fees_save(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step5.save_fees(request.user, p, request.POST), 'ردیف‌های عوارض ذخیره شد.')


@login_required
@require_POST
def permit_fees_offer(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step5.offer(request.user, p, request.POST), 'عوارض برای تایید متقاضی فرستاده شد.')


@login_required
@require_POST
def permit_fees_object(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step5.object_to(request.user, p, request.POST.get('notes', '')),
                        'اعتراض شما برای مسئول مالی فرستاده شد.')


@login_required
@require_POST
def permit_fees_approve(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step5.approve(request.user, p), 'عوارض تایید شد؛ پرونده به مرحله‌ی ۶ (تامین اجتماعی) رفت.')


@login_required
@require_POST
def permit_pay_add(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step5.add_payment(request.user, p, request.POST, request.FILES.getlist('slip')), 'پرداخت ثبت شد.')


@login_required
@require_POST
def permit_pay_confirm(request, file_id, pay_id):
    return _fees_action(request, file_id, lambda p: permit_step5.confirm_payment(request.user, p, pay_id), 'پرداخت تایید شد.')


@login_required
@require_POST
def permit_pay_remove(request, file_id, pay_id):
    return _fees_action(request, file_id, lambda p: permit_step5.remove_payment(request.user, p, pay_id), 'پرداخت حذف شد.')


@login_required
@require_POST
def permit_letter_issue(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step5.issue_letter(request.user, p, request.POST), 'معرفی‌نامه‌ی تامین اجتماعی صادر شد.')


@login_required
@require_POST
def permit_cert_submit(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step6.submit(request.user, p, request.POST, request.FILES.getlist('cert')),
                        'گواهی فرستاده شد؛ اصل آن را به دهیاری ببرید تا صحت آن بررسی شود.')


@login_required
@require_POST
def permit_cert_verify(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step6.verify(request.user, p, request.POST), 'گواهی تایید شد و پرونده به مرحله‌ی ۷ (صدور پروانه) رفت.')


@login_required
@require_POST
def permit_cert_return(request, file_id):
    return _fees_action(request, file_id, lambda p: permit_step6.send_back(request.user, p, request.POST.get('notes', '')), 'گواهی برای اصلاح به متقاضی برگشت داده شد.')


# ---------- step 7: the building permit form ----------

def _licence_groups(data):
    """The form fields grouped for the page: (title, [(key, label, value, choices or None)])."""
    def field(key, label):
        return (key, label, data.get(key, ''), permit_step7.CHOICES.get(key))
    sections = [
        ('مشخصات پروانه', [('kind', 'نوع پروانه'), ('permit_no', 'شماره‌ی پروانه'), ('issue_date', 'تاریخ صدور'),
                           ('fee_slip_no', 'عوارض زیربنا: شماره‌ی فیش'), ('fee_slip_date', 'تاریخ فیش'),
                           ('entry_slip_no', 'عوارض پذیره: شماره‌ی فیش'), ('entry_slip_date', 'تاریخ فیش پذیره'),
                           ('ins_slip_no', 'بیمه‌ی کارگران: شماره‌ی فیش'), ('ins_code', 'کد (شماره‌ی کارگاه)'),
                           ('finish_date', 'تاریخ اتمام عملیات ساختمانی'), ('finish_year', 'سال')]),
        ('ملک و مالک', [('registry_plot', 'شماره‌ی پلاک ثبتی'), ('section', 'بخش'), ('lot', 'قطعه'), ('zone', 'حوزه'), ('owner', 'نام و نام خانوادگی مالک'),
                        ('father', 'فرزند'), ('id_number', 'شماره‌ی شناسنامه'), ('issued_at', 'صادره از'), ('national_id', 'کد ملی'),
                        ('lawyer', 'وکیل قانونی'), ('lawyer_no', 'شماره‌ی وکالتنامه'), ('ownership', 'نوع مالکیت'), ('address', 'نشانی ملک'),
                        ('alley', 'کوچه'), ('plot_no', 'پلاک'), ('postal_code', 'کد پستی')]),
        ('مهندسان', [('sup_name', 'ناظر ساختمانی'), ('sup_license', 'شماره‌ی پروانه‌ی اشتغال'), ('sup_sign', 'شماره‌ی امضا'),
                     ('calc_name', 'محاسب'), ('calc_license', 'شماره‌ی پروانه‌ی محاسب'), ('calc_sign', 'شماره‌ی امضای محاسب'),
                     ('inst_name', 'تاسیسات'), ('inst_license', 'شماره‌ی پروانه‌ی تاسیسات'), ('inst_sign', 'شماره‌ی امضای تاسیسات'),
                     ('arch_name', 'ناظر معماری'), ('arch_license', 'شماره‌ی پروانه‌ی ناظر معماری'), ('arch_sign', 'شماره‌ی امضای ناظر معماری')]),
        ('وضعیت ملک (صفحه‌ی ۲)', [('existing', 'وضعیت موجود'), ('land', 'زمین'), ('trees', 'تعداد درخت'), ('deed_area', 'مساحت مطابق سند (م²)'),
                                  ('area_after', 'مساحت پس از اصلاحی (م²)'), ('density_pct', 'تراکم مجاز (٪)'), ('built_allowed', 'مساحت مجاز ساخت (م²)'),
                                  ('occupancy_m2', 'سطح اشغال (م²)'), ('aerial_code', 'کد نقشه‌ی هوایی')]),
        ('مشخصات ساختمان (صفحه‌ی ۳)', [('usage', 'نوع استفاده‌ی مجاز'), ('usage_other', 'سایر (توضیح)'), ('position', 'محل احداث بنا'), ('structure', 'نوع اسکلت'),
                                       ('roof', 'نوع سقف'), ('energy', 'گروه صرفه‌جویی انرژی'), ('checklist', 'چک لیست آیین‌نامه‌ی ۲۸۰۰ تکمیل شده'),
                                       ('material', 'مصالح'), ('material_other', 'مصالح دیگر'), ('trees_cut', 'تعداد درخت قابل قطع'), ('parking', 'تعداد پارکینگ'),
                                       ('bonyad_ref', 'یادداشت مجوز بنیاد'), ('notes_extra', 'یادداشت دیگر'),
                                       ('dehyari_name', 'نام دهیار'), ('tech_name', 'نام مسئول فنی')]),
    ]
    return [(title, [field(key, label) for key, label in rows]) for title, rows in sections]


@login_required
def permit_licence(request, file_id):
    """Step 7: the building permit form, prefilled for the staff to change, print and have signed by hand."""
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.stage_no < 7:
        messages.error(request, 'پروانه پس از تایید گواهی تامین اجتماعی صادر می‌شود.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    data = permit_step7.payload(permit)
    editing = staff and permit.licence_state != 'issued'
    return render(request, 'main/permits/licence.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'staff': staff, 'editing': editing, 'f': data, 'groups': _licence_groups(data),
        'sides': [(side, label, [(f'sd_{side}_{key}', text, data.get(f'sd_{side}_{key}', '')) for key, text in permit_step7.SIDE_FIELDS]) for side, label in permit_step7.SIDES],
        'floors': [(floor, label, [(f'fl_{floor}_{key}', text, data.get(f'fl_{floor}_{key}', '')) for key, text in permit_step7.FLOOR_FIELDS]) for floor, label in permit_step7.FLOORS],
        'issued': (permit.licence or {}).get('issued') or {},
        'am': permit_step7.am_payload(permit), 'am_fields': [(f'am_{k}', permit_step7.AM_LABELS[k], permit_step7.am_payload(permit).get(f'am_{k}', '')) for k in permit_step7.AM_TEXT],
        'am_sides': [(side, label, [(f'am_sd_{side}_{k}', text, permit_step7.am_payload(permit).get(f'am_sd_{side}_{k}', '')) for k, text in permit_step7.SIDE_FIELDS]) for side, label in permit_step7.AM_SIDES],
        'am_floors': [(floor, label, [(f'am_fl_{floor}_{k}', text, permit_step7.am_payload(permit).get(f'am_fl_{floor}_{k}', '')) for k, text in permit_step7.FLOOR_FIELDS]) for floor, label in permit_step7.FLOORS],
        'payload': {'f': {**data, **permit_step7.am_payload(permit)}, 'file': permit.pk, 'floors': [k for k, _ in permit_step7.FLOORS], 'sides': [k for k, _ in permit_step7.SIDES],
                    'choices': {k: dict(v) for k, v in permit_step7.CHOICES.items()}, 'letterhead': static('forms/permit/letterhead.jpg')},
    })


def _licence_action(request, file_id, action, ok):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_licence', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_licence_save(request, file_id):
    return _licence_action(request, file_id, lambda p: permit_step7.save(request.user, p, request.POST), 'اطلاعات فرم پروانه ذخیره شد.')


@login_required
@require_POST
def permit_licence_issue(request, file_id):
    return _licence_action(request, file_id, lambda p: permit_step7.issue(request.user, p, request.POST), 'صدور پروانه ثبت شد.')


# ---------- renewal of the permit's one-year term ----------

@login_required
def permit_extension_page(request, file_id):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.licence_state != 'issued':
        messages.error(request, 'تمدید پس از صدور پروانه ممکن است.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    open_ext = permit_extension.open_extension(permit)
    data = permit_extension.defaults(permit, open_ext or {})
    editing = bool(staff and open_ext)
    return render(request, 'main/permits/extension.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'staff': staff, 'editing': editing, 'info': permit_extension.expiry(permit),
        'open_ext': open_ext, 'done': permit_extension.issued_extensions(permit), 'can_request': (mine or staff) and permit_extension.can_request(permit),
        'max_renewals': permit_extension.MAX_RENEWALS, 'terms': permit_extension.TERMS, 'q': data['req'], 'e': data['form'],
        'payload': {**data, 'file': permit.pk, 'term': (open_ext or {}).get('term', 1), 'letterhead': static('forms/permit/letterhead.jpg')},
    })


def _extension_action(request, file_id, action, ok):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_extension', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_extension_request(request, file_id):
    return _extension_action(request, file_id, lambda p: permit_extension.request(request.user, p), 'درخواست تمدید باز شد؛ فرم را چاپ، امضا و با اثر انگشت به دهیاری بدهید.')


@login_required
@require_POST
def permit_extension_save(request, file_id):
    return _extension_action(request, file_id, lambda p: permit_extension.save(request.user, p, request.POST), 'فرم تمدید ذخیره شد.')


@login_required
@require_POST
def permit_extension_issue(request, file_id):
    return _extension_action(request, file_id, lambda p: permit_extension.issue(request.user, p, request.POST), 'تمدید ثبت شد.')


# ---------- supervision: forms 8-13, the technical supervisor, messages ----------

@login_required
def permit_supervision_page(request, file_id):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.licence_state != 'issued':
        messages.error(request, 'نظارت پس از صدور پروانه آغاز می‌شود.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    is_supervisor = permit.supervisor_id == request.user.id
    data = permit_supervision.payload(permit)
    now = permit_supervision.current(permit)
    active = permit.stage_no == 7 and now is not None
    steps = []
    for n in permit_supervision.NUMBERS:
        info = data[n]
        steps.append({'n': n, 'title': permit_supervision.TITLES[n], 'state': info['state'], 'text': permit_supervision.STATE_TEXT.get(info['state'], ''),
                      'now': n == now, 'docs': list(permit.documents.filter(pk__in=info['docs'], kind='supervision_form')),
                      'approved': info['state'] == 'approved' and info.get('approved_at', '')})
    cur = data.get(now) if now else None
    items = []
    if now in permit_supervision.ITEMS:
        for i, (label, a, b) in enumerate(permit_supervision.ITEMS[now], start=1):
            items.append({'i': i, 'label': label, 'a': a, 'b': b, 'v': cur['c'].get(str(i), '')})
    fields = [(key, permit_supervision.LABELS.get(key, key), cur['f'].get(key, '')) for key in ('number', 'date') + permit_supervision.FIELDS[now]] if cur else []
    return render(request, 'main/permits/supervision.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'staff': staff, 'is_supervisor': is_supervisor, 'steps': steps, 'now': now, 'cur': cur, 'items': items,
        'fields': fields, 'active': active, 'can_fill': active and permit_supervision.may_fill(request.user, permit) and cur['state'] in permit_supervision.OPEN_STATES,
        'can_upload': active and mine and cur['state'] in permit_supervision.OPEN_STATES, 'can_decide': active and staff,
        'supervisor': permit.supervisor, 'supervisors': permit_supervision.supervisors_for(permit) if staff else [],
        'commission': (permit.supervision or {}).get('commission') or [], 'thread': permit_supervision.thread(permit),
        'can_talk': mine or staff or is_supervisor, 'owner_name': permit.people.first().full_name,
        'payload': {'forms': {str(n): {'f': d['f'], 'c': d['c'], 'result': d['result'], 'notes': d['notes']} for n, d in data.items()}, 'file': permit.pk,
                    'now': now or 13, 'blank': {str(n): static(f'forms/permit/form{n:02d}_blank.jpg') for n in permit_supervision.NUMBERS},
                    'counts': {str(n): len(v) for n, v in permit_supervision.ITEMS.items()}},
    })


def _sup_action(request, file_id, action, ok):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_supervision', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_sup_fill(request, file_id, n):
    return _sup_action(request, file_id, lambda p: permit_supervision.fill(request.user, p, n, request.POST), 'اطلاعات فرم ذخیره شد.')


@login_required
@require_POST
def permit_sup_upload(request, file_id, n):
    return _sup_action(request, file_id, lambda p: permit_supervision.upload(request.user, p, n, request.FILES.getlist('signed')),
                       'فرم امضاشده فرستاده شد؛ دهیاری آن را تایید می‌کند.')


@login_required
@require_POST
def permit_sup_approve(request, file_id, n):
    return _sup_action(request, file_id, lambda p: permit_supervision.approve(request.user, p, n), 'فرم تایید شد.')


@login_required
@require_POST
def permit_sup_return(request, file_id, n):
    return _sup_action(request, file_id, lambda p: permit_supervision.send_back(request.user, p, n, request.POST.get('notes', '')), 'فرم برگشت داده شد.')


@login_required
@require_POST
def permit_sup_refer(request, file_id, n):
    return _sup_action(request, file_id, lambda p: permit_supervision.refer(request.user, p, n, request.POST), 'تخلف به کمیسیون ماده ۹۹ ارجاع شد.')


@login_required
@require_POST
def permit_sup_decide(request, file_id, n):
    return _sup_action(request, file_id, lambda p: permit_supervision.decide(request.user, p, n, request.POST), 'رای کمیسیون ثبت شد.')


@login_required
@require_POST
def permit_sup_assign(request, file_id):
    return _sup_action(request, file_id, lambda p: permit_supervision.assign(request.user, p, request.POST.get('supervisor') or None), 'ناظر فنی پرونده ثبت شد.')


@login_required
@require_POST
def permit_sup_message(request, file_id):
    return _sup_action(request, file_id, lambda p: permit_supervision.post_message(request.user, p, request.POST.get('text', '')), 'پیام فرستاده شد.')


@login_required
@require_POST
def permit_licence_amend(request, file_id):
    return _licence_action(request, file_id, lambda p: permit_step7.save_amendment(request.user, p, request.POST), 'فرم اصلاحات و تغییرات ذخیره شد.')


# ---------- services: letters for electricity, gas and water ----------

@login_required
def permit_services_page(request, file_id):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.licence_state != 'issued':
        messages.error(request, 'نامه‌ی خدمات پس از صدور پروانه ممکن است.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    items = permit_services.services(permit)
    wanted = request.GET.get('s', '')
    chosen = next((s for s in items if str(s['id']) == wanted), None) or next((s for s in reversed(items) if s['state'] in ('requested', 'approved')), None)
    rows = [{**s, 'title': permit_services.KINDS[s['kind']]['title'], 'text': permit_services.STATE_TEXT.get(s['state'], ''), 'on': chosen is not None and s['id'] == chosen['id']}
            for s in reversed(items)]
    data = permit_services.payload(permit, chosen) if chosen else {}
    kind = permit_services.KINDS[chosen['kind']] if chosen else None
    return render(request, 'main/permits/services.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'staff': staff, 'rows': rows, 'chosen': chosen, 'kind': kind,
        'kinds': [(k, v['title']) for k, v in permit_services.KINDS.items()], 'can_request': mine or staff,
        'fields': [(key, permit_services.LABELS[key], data.get(key, '')) for key in (kind['fields'] + ('number', 'date', 'dehyari_name') if kind else ())],
        'editing': bool(chosen and staff and chosen['state'] in ('requested', 'approved')), 'printable': bool(chosen and chosen['state'] in ('approved', 'issued')),
        'extra': [(key, permit_services.LABELS[key]) for key in ('permit_no', 'permit_date', 'endwork_no', 'endwork_date', 'ref_no', 'ref_date', 'slip_no', 'slip_date')],
        'payload': {'f': data, 'kind': chosen['kind'] if chosen else '', 'title': kind['title'] if kind else '', 'company': kind['company'] if kind else '',
                    'pages': kind['pages'] if kind else 1, 'what': kind['what'] if kind else '', 'file': permit.pk, 'letterhead': static('forms/permit/letterhead.jpg'),
                    'state': chosen['state'] if chosen else ''},
    })


def _svc_action(request, file_id, action, ok, sid=None):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    params = ([f's={sid}'] if sid else []) + (['embed=1'] if request.POST.get('embed') else [])
    suffix = ('?' + '&'.join(params)) if params else ''
    return redirect(reverse('main:permit_services', args=[permit.pk]) + suffix)


@login_required
@require_POST
def permit_service_request(request, file_id):
    return _svc_action(request, file_id, lambda p: permit_services.request(request.user, p, request.POST.get('kind', ''), request.POST), 'درخواست ثبت شد؛ دهیاری آن را بررسی می‌کند.')


@login_required
@require_POST
def permit_service_save(request, file_id, sid):
    return _svc_action(request, file_id, lambda p: permit_services.save(request.user, p, sid, request.POST), 'نامه ذخیره شد.', sid)


@login_required
@require_POST
def permit_service_approve(request, file_id, sid):
    return _svc_action(request, file_id, lambda p: permit_services.approve(request.user, p, sid, request.POST), 'نامه تایید شد؛ متقاضی می‌تواند آن را چاپ کند.', sid)


@login_required
@require_POST
def permit_service_reject(request, file_id, sid):
    return _svc_action(request, file_id, lambda p: permit_services.reject(request.user, p, sid, request.POST.get('reason', '')), 'درخواست رد شد.', sid)


@login_required
@require_POST
def permit_service_cancel(request, file_id, sid):
    return _svc_action(request, file_id, lambda p: permit_services.cancel(request.user, p, sid), 'درخواست لغو شد.')


@login_required
@require_POST
def permit_service_issue(request, file_id, sid):
    return _svc_action(request, file_id, lambda p: permit_services.issue(request.user, p, sid, request.POST), 'تحویل نامه ثبت شد.', sid)


# ---------- the end-of-work certificate ----------

@login_required
def permit_endwork_page(request, file_id):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if not permit_endwork.available(permit):
        messages.error(request, 'درخواست پایان کار پس از تایید همه‌ی فرم‌های نظارت ممکن است.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    data = permit_endwork.payload(permit)
    state = permit.endwork_state
    return render(request, 'main/permits/endwork.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'staff': staff, 'state': state, 'state_text': permit_endwork.STATE_TEXT.get(state, ''),
        'info': permit.endwork or {}, 'can_request': (mine or staff) and state in ('', 'rejected'), 'editing': staff and state in ('requested', 'approved'),
        'printable': state in ('approved', 'issued') and (staff or mine),
        'fields': [(key, permit_endwork.LABELS[key], data.get(key, '')) for key in permit_endwork.KEYS],
        'sides': [(side, label, data.get(f'sd_{side}_deed', ''), data.get(f'sd_{side}_after', '')) for side, label in (('north', 'شمالاً'), ('east', 'شرقاً'), ('south', 'جنوباً'), ('west', 'غرباً'))],
        'floors': [(floor, label, data.get(f'fl_{floor}_count', ''), data.get(f'fl_{floor}_area', ''), data.get(f'fl_{floor}_use', '')) for floor, label in permit_endwork.FLOORS],
        'payload': {'f': data, 'file': permit.pk, 'floors': [k for k, _ in permit_endwork.FLOORS], 'letterhead': static('forms/permit/letterhead.jpg')},
    })


def _end_action(request, file_id, action, ok):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_endwork', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_endwork_request(request, file_id):
    return _end_action(request, file_id, lambda p: permit_endwork.request(request.user, p), 'درخواست پایان کار ثبت شد؛ دهیاری پاسخ می‌دهد.')


@login_required
@require_POST
def permit_endwork_save(request, file_id):
    return _end_action(request, file_id, lambda p: permit_endwork.save(request.user, p, request.POST), 'اطلاعات گواهی ذخیره شد.')


@login_required
@require_POST
def permit_endwork_approve(request, file_id):
    return _end_action(request, file_id, lambda p: permit_endwork.approve(request.user, p, request.POST), 'درخواست تایید شد؛ گواهی قابل چاپ است.')


@login_required
@require_POST
def permit_endwork_reject(request, file_id):
    return _end_action(request, file_id, lambda p: permit_endwork.reject(request.user, p, request.POST.get('reason', '')), 'درخواست رد شد.')


@login_required
@require_POST
def permit_endwork_issue(request, file_id):
    return _end_action(request, file_id, lambda p: permit_endwork.issue(request.user, p, request.POST), 'صدور گواهی پایان ساخت ثبت شد.')


# ---------- construction without a permit, step 2: the request form and the undertaking ----------

@login_required
def permit_commission_page(request, file_id):
    permit = permit_commission.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.stage_no < 2 or permit.state != 'done':
        messages.error(request, 'این بخش پس از تایید مرحله‌ی ۱ در دسترس است.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    data = permit_commission.payload(permit)
    at_step = permit_commission.at_step(permit)
    return render(request, 'main/permits/commission.html', {
        'permit': permit, 'd': data, 'embed': embed, 'mine': mine, 'staff': staff,
        'scan_rows': [(key, permit_commission.LABELS[key], docs) for key, docs in permit_commission.scans(permit).items()],
        'can_edit': at_step and permit_commission._may_edit(request.user, permit),          # pylint: disable=protected-access
        'owner_open': at_step and mine and permit.commission_state in permit_commission.OPEN_STATES,
        'can_decide': at_step and staff and permit.commission_state == 'uploaded',
        'field_rows': [(key, label, data['form'].get(key, '')) for key, label in COMMISSION_FIELDS],
        'payload': {**data, 'owner': data['form']['name']},
    })


def _commission_action(request, file_id, action, ok):
    permit = permit_commission.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_commission', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_commission_save(request, file_id):
    return _commission_action(request, file_id, lambda p: permit_commission.save_form(request.user, p, request.POST), 'اطلاعات فرم‌ها ذخیره شد.')


@login_required
@require_POST
def permit_commission_upload(request, file_id):
    return _commission_action(request, file_id, lambda p: permit_commission.upload(request.user, p, request.POST, request.FILES),
                              'فرم‌های امضاشده فرستاده شد؛ دهیاری آن‌ها را بررسی می‌کند.')


@login_required
@require_POST
def permit_commission_verify(request, file_id):
    return _commission_action(request, file_id, lambda p: permit_commission.verify(request.user, p, request.POST),
                              'فرم‌ها تایید شد و پرونده به مرحله‌ی ۳ رفت.')


@login_required
@require_POST
def permit_commission_return(request, file_id):
    return _commission_action(request, file_id, lambda p: permit_commission.send_back(request.user, p, request.POST.get('notes', '')),
                              'فرم‌ها برای اصلاح به متقاضی برگشت داده شد.')


# ---------- construction without a permit, step 3: the warning notice the owner received ----------

@login_required
def permit_notice_page(request, file_id):
    permit = permit_notice.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    embed = bool(request.GET.get('embed'))
    if permit.stage_no < 3 or permit.state != 'done':
        messages.error(request, 'این بخش پس از تایید مرحله‌ی ۲ در دسترس است.')
        return redirect(_file_url(permit, embed))
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    at_step = permit_notice.at_step(permit)
    owner_open = at_step and mine and permit.notice_state in permit_notice.OPEN_STATES
    can_decide = at_step and staff and permit.notice_state == 'uploaded'
    return render(request, 'main/permits/notice.html', {
        'permit': permit, 'embed': embed, 'mine': mine, 'n': permit_notice.data(permit), 'scans': permit_notice.documents(permit),
        'owner_open': owner_open, 'can_decide': can_decide, 'editable': owner_open or can_decide,
        'checks': permit_notice.checks(permit) if (can_decide or (staff and permit.notice_state)) else [],
        'positions': permit_notice.POSITIONS.items(), 'deliveries': permit_notice.DELIVERIES.items(),
        'checked': (permit.notice or {}).get('checked') or {},
    })


def _notice_action(request, file_id, action, ok):
    permit = permit_notice.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect(reverse('main:permit_notice', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') else ''))


@login_required
@require_POST
def permit_notice_upload(request, file_id):
    return _notice_action(request, file_id, lambda p: permit_notice.upload(request.user, p, request.POST, request.FILES),
                          'اخطاریه فرستاده شد؛ دهیاری آن را بررسی می‌کند.')


@login_required
@require_POST
def permit_notice_verify(request, file_id):
    return _notice_action(request, file_id, lambda p: permit_notice.verify(request.user, p, request.POST),
                          'اخطاریه تایید شد و پرونده به مرحله‌ی ۴ رفت.')


@login_required
@require_POST
def permit_notice_return(request, file_id):
    return _notice_action(request, file_id, lambda p: permit_notice.send_back(request.user, p, request.POST.get('notes', '')),
                          'اخطاریه برای اصلاح به متقاضی برگشت داده شد.')


# ---------- construction without a permit, step 1: the defence form and the shamim sketch ----------

def _step1_redirect(request, permit, name):
    return redirect(reverse(f'main:{name}', args=[permit.pk]) + ('?embed=1' if request.POST.get('embed') or request.GET.get('embed') else ''))


@login_required
def permit_defence_page(request, file_id):
    permit = permit_defence.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    mine = permit.request.user_id == request.user.id
    staff = permits.may_open(request.user, permit)
    data = permit_defence.payload(permit)
    return render(request, 'main/permits/defence.html', {
        'permit': permit, 'embed': bool(request.GET.get('embed')), 'mine': mine, 'staff': staff, 'd': data,
        'scans': permit_defence.scans(permit), 'can_edit': permit_defence._may_edit(request.user, permit),          # pylint: disable=protected-access
        'owner_open': mine and permit_defence.at_step(permit),
        'field_rows': [(key, label, data['form'].get(key, '')) for key, label in DEFENCE_FIELDS],
        'statuses': permit_defence.STATUSES.items(), 'suggestions': permit_defence.SUGGESTIONS,
        'payload': {**data, 'suggestions': list(permit_defence.SUGGESTIONS)},
    })


def _defence_action(request, file_id, action, ok):
    permit = permit_defence.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return _step1_redirect(request, permit, 'permit_defence')


@login_required
@require_POST
def permit_defence_save(request, file_id):
    return _defence_action(request, file_id, lambda p: permit_defence.save_form(request.user, p, request.POST), 'اطلاعات فرم دفاعیه ذخیره شد.')


@login_required
@require_POST
def permit_defence_upload(request, file_id):
    return _defence_action(request, file_id, lambda p: permit_defence.upload(request.user, p, request.FILES),
                           'فرم دفاعیه‌ی امضاشده فرستاده شد.')


@login_required
def permit_sketch_page(request, file_id):
    permit = permit_sketch.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    mine = permit.request.user_id == request.user.id
    at_step = permit_sketch.at_step(permit)
    work = permit_sketch.may_work(request.user, permit)
    return render(request, 'main/permits/sketch.html', {
        'permit': permit, 'embed': bool(request.GET.get('embed')), 'mine': mine, 'sk': permit.sketch or {}, 'state': permit.sketch_state,
        'slips': permit_sketch.slips(permit), 'sketch_files': permit_sketch.sketch_files(permit),
        'can_request': at_step and mine and not permit.sketch_state and not permit_sketch.sketch_files(permit),
        'can_price': at_step and work and permit.sketch_state in ('requested', 'priced'),
        'can_pay': at_step and mine and permit.sketch_state == 'priced',
        'can_deliver': at_step and work and permit.sketch_state == 'paid',
    })


def _sketch_action(request, file_id, action, ok):
    permit = permit_sketch.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    try:
        action(permit)
        messages.success(request, ok)
    except (OfficeError, lifecycle.TransitionError) as exc:
        messages.error(request, str(exc))
    return _step1_redirect(request, permit, 'permit_sketch')


@login_required
@require_POST
def permit_sketch_request(request, file_id):
    return _sketch_action(request, file_id, lambda p: permit_sketch.request(request.user, p), 'درخواست کروکی ثبت شد؛ مسئول فنی هزینه را تعیین می‌کند.')


@login_required
@require_POST
def permit_sketch_fee(request, file_id):
    return _sketch_action(request, file_id, lambda p: permit_sketch.set_fee(request.user, p, request.POST), 'هزینه‌ی کروکی تعیین و به متقاضی اطلاع داده شد.')


@login_required
@require_POST
def permit_sketch_pay(request, file_id):
    return _sketch_action(request, file_id, lambda p: permit_sketch.pay(request.user, p, request.POST, request.FILES), 'فیش ثبت شد؛ منتظر تایید پرداخت و تحویل کروکی باشید.')


@login_required
@require_POST
def permit_sketch_deliver(request, file_id):
    return _sketch_action(request, file_id, lambda p: permit_sketch.deliver(request.user, p, request.POST, request.FILES), 'پرداخت تایید و کروکی تحویل شد.')

