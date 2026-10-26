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
from main.office import permit_form, permit_step2, permit_step3, permit_step4, permits
from main.access import can
from main.office.errors import OfficeError
from main.roles import CITIZEN_ROLES

INLINE_TYPES = {'.pdf', '.jpg', '.jpeg', '.png'}
PERSON_LABELS = (('name', 'نام و نام خانوادگی'), ('father', 'فرزند'), ('grade', 'پایه‌ی پروانه‌ی اشتغال'), ('field', 'رشته'), ('license', 'شماره‌ی پروانه / عضویت'))
FORM_LABELS = (('f04', 'فرم ۰۴ (دستور تهیه‌ی نقشه)'), ('f05', 'فرم ۰۵ (تعهد سازه)'), ('f06', 'فرم ۰۶ (تعهد معماری)'), ('f07', 'فرم ۰۷ (تعهد نظارت)'))
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


@login_required
def building_permit_form(request):
    """Step 1: the applicant fills in the file (owner, property, ownership paper, identity papers, shamim file)."""
    if role_of(request.user) not in CITIZEN_ROLES:
        messages.error(request, 'درخواست پروانه ساختمان را شهروند ثبت می‌کند.')
        return redirect('main:dashboard')
    values, errors = permits.prefill(request.user), {}
    if request.method == 'POST':
        data, errors = permit_form.parse(request.POST, request.FILES)
        if not errors:
            try:
                permit = permits.submit(request.user, data)
            except lifecycle.TransitionError as exc:        # the plot is locked: lifecycle words the refusal
                errors = {'renewal_code': str(exc)}
            else:
                messages.success(request, 'پرونده‌ی پروانه ساختمان ثبت شد؛ کارشناس مدارک را بررسی و پرونده را افتتاح می‌کند.')
                return redirect(_file_url(permit, embed=bool(request.GET.get('embed'))))
        values = permit_form.keep_for_redisplay(request.POST)
    return render(request, 'main/services/building-permits/step1.html', {
        'v': values, 'errors': errors, 'profile': request.user.profile, 'co_rows': _co_rows(values, errors),
        'land_uses': PermitFile.LAND_USES, 'kinds': PermitFile.KINDS,
        'co_roles': [(r, label) for r, label in PermitPerson.ROLES if r != 'applicant'],
    }, status=400 if errors else 200)


@login_required
def permit_file(request, file_id):
    permit = permits.find(request.user, file_id)
    if permit is None:
        raise Http404('پرونده پیدا نشد.')
    mine = permit.request.user_id == request.user.id
    can_decide = permits.may_open(request.user, permit)
    people = list(permit.people.prefetch_related('documents'))
    return render(request, 'main/permits/detail.html', {
        'permit': permit, 'sr': permit.request, 'people': people, 'tracker': permits.tracker(permit),
        'file_documents': permit.documents.filter(person__isnull=True), 'mine': mine, 'can_decide': can_decide,
        'staff_view': not mine, 'embed': bool(request.GET.get('embed')),
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
    if doc is None or permits.find(request.user, doc.file_id) is None:
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
    permit = permits.find(request.user, file_id)
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
    permit = permits.find(request.user, file_id)
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
    permit = permits.find(request.user, file_id)
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
