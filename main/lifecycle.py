"""ServiceRequest lifecycle: the only place that creates a request or changes its status.

Views call a verb (``submit``, ``approve``, ``reject``, ...) and render the outcome. Each
verb checks the transition is allowed, updates status / workflow stage, writes
the workflow history entry and notifies the people involved.

``authority`` selects the wording used for the municipality head ('mayor') or
for the municipal expert ('expert').
"""
from django.utils import timezone

from main.models import CityVillage, County, Inspection, Province, ServiceRequest
from main.notifications import notify

FINAL_STATUSES = {'completed'}
VALID_STATUSES = {value for value, _ in ServiceRequest.STATUS_CHOICES}

REFERRAL_STAGES = {
    'council': ('council_review', 'شورای اسلامی روستا'),
    'inspector': ('inspection', 'ناظر فنی'),
    'accountant': ('finance_review', 'مسئول مالی'),
    'dehyari': ('mayor_review', 'دهیار / شهردار'),
    'engineer': ('expert_review', 'کارشناس دهیاری'),
}


class TransitionError(Exception):
    """The requested change is not allowed for this request."""


def _ensure_open(sr):
    if sr.status in FINAL_STATUSES:
        raise TransitionError('درخواست تکمیل شده است و قابل تغییر نیست.')


def _ensure_not_locked(sr):
    """A request for a locked plot (debt, neighbour's complaint, street occupation) cannot be approved."""
    from main.gis import locks
    message = locks.refusal(sr.parcel_number) if sr.parcel_number else ''
    if message:
        raise TransitionError(message)


def _profile_geography(user):
    """Province, county and village of the user's profile as model instances (None where unknown)."""
    prof = getattr(user, 'profile', None)
    if not prof:
        return {}
    village = CityVillage.objects.filter(name=prof.city_village).first() if prof.city_village else None
    if not village and prof.city_village_name:
        village = CityVillage.objects.filter(name=prof.city_village_name).first()
    return {
        'province': Province.objects.filter(name=prof.province).first() if prof.province else None,
        'county': County.objects.filter(name=prof.county).first() if prof.county else None,
        'city_village': village,
    }


def submit(user, *, action, instance=None, **fields):
    """A citizen files a request: the one way a ServiceRequest is created.

    Refuses a locked plot, fills the province / county / village the caller left empty from the user's
    profile, starts the workflow at the municipal expert and writes the first history entry.
    ``instance`` is an unsaved request (a ModelForm's ``save(commit=False)``); ``fields`` are set on it.
    """
    sr = instance if instance is not None else ServiceRequest()
    for name, value in fields.items():
        setattr(sr, name, value)
    _ensure_not_locked(sr)
    sr.user = user
    chosen = getattr(getattr(user, 'profile', None), 'active_municipality', None)
    if chosen is not None and sr.target_municipality_id is None:
        sr.target_municipality = chosen          # a citizen who switched municipality files with the new one
    sr.status = 'pending'
    sr.workflow_stage = 'expert_review'
    sr.referral_target = 'engineer'
    for name, value in _profile_geography(user).items():
        if value is not None and getattr(sr, f'{name}_id') is None:
            setattr(sr, name, value)
    sr.add_workflow_step(action=action, from_user=user, to_role='engineer')
    sr.save()
    return sr


def _finish(sr, actor, *, status, stage, action, notes='', to_role='citizen', reviewed=False):
    sr.status = status
    sr.workflow_stage = stage
    if reviewed:
        sr.reviewed_at = timezone.now()
    sr.add_workflow_step(action=action, from_user=actor, to_role=to_role, notes=notes)
    sr.save()


def approve(sr, actor, *, notes='', completed=False, authority='expert'):
    _ensure_open(sr)
    _ensure_not_locked(sr)
    if authority == 'mayor':
        _finish(sr, actor, status='approved', stage='approved', reviewed=True,
                action='approved', notes='تایید نهایی توسط دهیار/شهردار انجام شد.')
        notify(sr.user, 'درخواست تایید شد',
               f'درخواست "{sr.title}" شما توسط دهیاری تایید شد.', request=sr)
        return
    sr.staff_comments = (sr.staff_comments or '') + f"\n[تایید کارشناس: {notes}]"
    _finish(sr, actor, status='completed' if completed else 'approved', stage='approved',
            reviewed=True, action='تایید پرونده توسط کارشناس دهیاری', notes=notes)
    notify(sr.user, f'تایید درخواست: {sr.title}',
           f'درخواست شما توسط کارشناس دهیاری تایید گردید. {notes}', request=sr)


def reject(sr, actor, reason, *, authority='expert'):
    _ensure_open(sr)
    if authority == 'mayor':
        sr.staff_comments = reason
        _finish(sr, actor, status='rejected', stage='rejected', reviewed=True,
                action='rejected', notes=f'درخواست توسط دهیار/شهردار رد شد: {reason}')
        notify(sr.user, 'درخواست رد شد',
               f'درخواست "{sr.title}" شما رد شد. دلیل: {reason}', request=sr)
        return
    sr.staff_comments = (sr.staff_comments or '') + f"\n[رد کارشناس: {reason}]"
    _finish(sr, actor, status='rejected', stage='rejected',
            action='رد پرونده توسط کارشناس دهیاری', notes=reason)
    notify(sr.user, f'رد درخواست: {sr.title}',
           f'درخواست شما توسط کارشناس دهیاری رد شد. دلیل: {reason}', request=sr)


def request_documents(sr, actor, notes):
    _ensure_open(sr)
    sr.staff_comments = (sr.staff_comments or '') + f"\n[نیاز به مدارک: {notes}]"
    _finish(sr, actor, status='requires_documents', stage='requires_documents',
            action='اعلام نقص مدارک به متقاضی', notes=notes)
    notify(sr.user, f'نیاز به رفع نقص مدارک: {sr.title}',
           f'کارشناس دهیاری اعلام نقص مدارک نمود: {notes}. '
           'لطفاً مدارک خواسته شده را در پنل کاربری بارگذاری نمایید.', request=sr)


def refer(sr, actor, target_role, *, notes='', assigned_user=None):
    """Forward the request to another panel. Returns (new_stage, target_name)."""
    _ensure_open(sr)
    if target_role not in REFERRAL_STAGES:
        raise TransitionError('نقش مقصد نامعتبر است.')
    new_stage, target_name = REFERRAL_STAGES[target_role]
    if assigned_user:
        sr.assigned_to = assigned_user
    sr.referral_target = target_role
    sr.referral_notes = notes
    sr.referral_date = timezone.now()
    if target_role == 'inspector' and assigned_user:
        Inspection.objects.get_or_create(
            request=sr, inspector=assigned_user,
            defaults={'status': 'pending',
                      'notes': notes or 'ارجاع شده از کارشناس دهیاری جهت بازرسی میدانی'},
        )
    _finish(sr, actor, status='in_review', stage=new_stage,
            action=f'ارجاع پرونده به {target_name}', notes=notes, to_role=target_role)
    suffix = f' دستور: {notes}' if notes else ''
    notify(sr.user, f'ارجاع درخواست: {sr.title}',
           f'پرونده شما توسط کارشناس دهیاری جهت بررسی به «{target_name}» ارجاع گردید.' + suffix,
           request=sr)
    if assigned_user:
        notify(assigned_user, f'پرونده ارجاعی جدید: {sr.title}',
               f'پرونده کد #{sr.id} ({sr.get_request_type_display()}) توسط کارشناس دهیاری '
               'جهت اقدام برای شما ارسال شد.' + suffix, request=sr)
    return new_stage, target_name


def assign(sr, actor, staff_user):
    """Mayor hands the request to a staff member for review."""
    _ensure_open(sr)
    sr.assigned_to = staff_user
    sr.status = 'in_review'
    sr.add_workflow_step(action='ارجاع به کارشناس', from_user=actor, to_role='engineer')
    sr.save()
    notify(staff_user, 'درخواست جدید ارجاع شده',
           f'درخواست "{sr.title}" به شما ارجاع شد.', request=sr)
    notify(sr.user, 'درخواست در حال بررسی',
           f'درخواست "{sr.title}" شما به کارشناس ارجاع شد و در حال بررسی است.', request=sr)


def set_status(sr, actor, new_status, notes=''):
    """Generic staff status change (status screen)."""
    if new_status not in VALID_STATUSES:
        raise TransitionError('وضعیت نامعتبر است.')
    _ensure_open(sr)
    if new_status in ('approved', 'completed'):
        _ensure_not_locked(sr)
    sr.status = new_status
    sr.workflow_stage = new_status if new_status in dict(sr.WORKFLOW_STAGES) else sr.workflow_stage
    if notes:
        sr.staff_comments = (sr.staff_comments or '') + f'\n[{notes}]'
    sr.add_workflow_step(action=f'تغییر وضعیت به {sr.get_status_display()}',
                         from_user=actor, to_role='citizen', notes=notes)
    sr.save()
    notify(sr.user, 'وضعیت درخواست به‌روز شد',
           f'وضعیت درخواست {sr.title} به {sr.get_status_display()} تغییر کرد.', request=sr)


def record_inspection(sr, inspector, *, approved, reason=''):
    """The inspector's outcome decides the request (approved / rejected)."""
    _ensure_open(sr)
    if approved:
        _ensure_not_locked(sr)
        _finish(sr, inspector, status='approved', stage='approved', reviewed=True,
                action='تایید بازرسی توسط ناظر فنی', to_role='citizen')
        notify(sr.user, 'بازرسی تکمیل شد',
               f'بازرسی درخواست {sr.title} با موفقیت تکمیل شد.', request=sr)
    else:
        _finish(sr, inspector, status='rejected', stage='rejected', reviewed=True,
                action='رد بازرسی توسط ناظر فنی', notes=reason, to_role='citizen')
        notify(sr.user, 'بازرسی رد شد',
               f'بازرسی درخواست {sr.title} رد شد. دلیل: {reason}', request=sr)


def permit_opened(sr, actor, *, code, notes=''):
    """Step 1 of a building permit (افتتاح پرونده) is done: the file has its renewal code and moves on."""
    _ensure_open(sr)
    sr.parcel_number = code
    _ensure_not_locked(sr)
    _finish(sr, actor, status='in_review', stage='expert_review',
            action=f'افتتاح پرونده پروانه و ثبت کد نوسازی {code}', notes=notes, to_role='engineer')
    what = 'ساخت‌وساز بدون پروانه' if sr.request_type == 'no_permit' else 'پروانه ساختمان'
    notify(sr.user, f'پرونده شما تایید شد: {sr.title}' if sr.request_type == 'no_permit' else f'پرونده شما افتتاح شد: {sr.title}',
           f'مرحله‌ی ۱ پرونده‌ی {what} شما تایید شد و کد نوسازی ملک شما {code} است. مرحله‌ی بعد را در پرونده ببینید.', request=sr)


def permit_resubmitted(sr, actor):
    """The applicant added the missing papers: the file is waiting for the staff again."""
    _ensure_open(sr)
    _finish(sr, actor, status='pending', stage='expert_review', action='ارسال مجدد مدارک توسط متقاضی',
            to_role='engineer')
