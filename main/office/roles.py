"""Giving and taking back staff roles. The dehyari acts inside their own village only."""
from django.db import transaction
from django.utils import timezone

from main.models import Municipality, RoleGrant, UserProfile
from main.notifications import notify
from main.office.errors import Forbidden, Invalid, NotFound

GRANTABLE = ('accountant', 'engineer', 'inspector', 'council')
PROTECTED = ('admin', 'dehyari')
ROLE_ICONS = {'accountant': 'fa-calculator', 'engineer': 'fa-helmet-safety',
              'inspector': 'fa-clipboard-check', 'council': 'fa-landmark'}


def is_admin(user):
    return user.is_superuser or getattr(getattr(user, 'profile', None), 'role', None) == 'admin'


def village_of(actor):
    """Village name the actor administers; None for an admin (all villages)."""
    if is_admin(actor):
        return None
    municipality = Municipality.objects.filter(admin_user=actor).first()
    if municipality is None:
        raise NotFound('دهیاری شما یافت نشد.')
    return municipality.city_village


def municipality_for(profile):
    return Municipality.objects.filter(city_village=profile.city_village).first() if profile.city_village else None


def _target(actor, user_id):
    if str(user_id) == str(actor.id):
        raise Forbidden('نقش این حساب از اینجا قابل تغییر نیست.')
    village = village_of(actor)
    profile = UserProfile.objects.select_related('user').filter(user_id=user_id).first()
    if profile is None or (village is not None and profile.city_village != village):
        raise NotFound('کاربر در دهیاری شما یافت نشد.')
    if profile.role in PROTECTED:
        raise Forbidden('نقش این حساب از اینجا قابل تغییر نیست.')
    return profile


def grant_role(actor, user_id, role):
    """Give ``role`` to the user. Returns (grant, changed); granting the same role again is a no-op."""
    if role not in GRANTABLE:
        raise Invalid('نقش انتخاب‌شده معتبر نیست.')
    with transaction.atomic():
        profile = _target(actor, user_id)
        active = RoleGrant.objects.filter(user=profile.user, revoked_at__isnull=True).first()
        if profile.role == role and active:
            return active, False
        now = timezone.now()
        RoleGrant.objects.filter(user=profile.user, revoked_at__isnull=True).update(revoked_at=now, revoked_by=actor)
        grant = RoleGrant.objects.create(
            user=profile.user, role=role, previous_role=profile.role, granted_by=actor,
            municipality=municipality_for(profile))
        profile.role = role
        profile.save(update_fields=['role'])
        notify(profile.user, 'نقش جدید در سامانه',
               f'دهیاری نقش «{profile.get_role_display()}» را به حساب شما اختصاص داد.', kind='admin_notice')
        return grant, True


def revoke_role(actor, user_id):
    """Return the user to citizen. Returns True when something changed."""
    with transaction.atomic():
        profile = _target(actor, user_id)
        if profile.role not in GRANTABLE:
            return False
        RoleGrant.objects.filter(user=profile.user, revoked_at__isnull=True).update(
            revoked_at=timezone.now(), revoked_by=actor)
        profile.role = 'citizen'
        profile.save(update_fields=['role'])
        notify(profile.user, 'پایان نقش سازمانی',
               'نقش سازمانی شما توسط دهیاری برداشته شد و حساب شما به شهروند بازگشت.', kind='admin_notice')
        return True


def staff_and_candidates(actor, query=''):
    """(current staff, matching candidates) for the roles page."""
    village = village_of(actor)
    people = UserProfile.objects.select_related('user').filter(is_active=True)
    if village is not None:
        people = people.filter(city_village=village)
    staff = people.filter(role__in=GRANTABLE).order_by('role', 'user__last_name')
    candidates = people.exclude(role__in=PROTECTED + GRANTABLE).exclude(user=actor)
    query = (query or '').strip()
    if query:
        from django.db.models import Q
        candidates = candidates.filter(
            Q(user__username__icontains=query) | Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) | Q(national_id__icontains=query) |
            Q(mobile_number__icontains=query))
    else:
        candidates = candidates.none()   # never list a whole village: the dehyari searches by name/ID
    return staff, candidates.order_by('user__last_name')[:20]
