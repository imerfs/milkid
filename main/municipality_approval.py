"""Dehyari account of a municipality: created inactive at registration, activated on approval.

Registration only *requests* a place. Nothing about existing places or accounts changes until an
admin approves, so a stranger cannot unseat the current dehyari by filling in a form.
"""
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from main.geography import norm
from main.models import CityVillage, District, Notification, UserProfile


def create_pending_manager(municipality, data):
    """Create the inactive dehyari account from the registration form data and link it."""
    first, _, last = (data['manager_name'] or '').strip().partition(' ')
    user = User(username=data['manager_username'], email=data.get('manager_email', ''),
                first_name=first, last_name=last, is_active=False)
    user.set_password(data['manager_password'])
    user.save()

    profile = user.profile
    profile.national_id = data['manager_national_id']
    profile.mobile_number = data['manager_phone']
    profile.role = 'citizen'            # becomes 'dehyari' only when an admin approves the municipality
    profile.is_verified = False
    profile.approval_status = 'pending'
    profile.is_village = municipality.municipality_type == 'dehyari'
    for name in ('province', 'county', 'district', 'city_village'):
        setattr(profile, name, getattr(municipality, name))
    profile.city_village_name = municipality.city_village
    profile.save()

    municipality.admin_user = user
    municipality.manager_user = user
    municipality.save(update_fields=['admin_user', 'manager_user'])
    return user


def _settlement_type(municipality):
    return 'village' if municipality.municipality_type == 'dehyari' else 'city'


def ensure_settlement(municipality):
    """The CityVillage row of the municipality's place: found, or created when it does not exist yet."""
    municipality.save()                   # refreshes the *_fk links from the text
    if municipality.city_village_fk_id:
        settlement = municipality.city_village_fk
    else:
        district = municipality.district_fk
        if district is None and municipality.county_fk_id:
            district = District.objects.filter(county=municipality.county_fk).order_by('id').first()
        if district is None:
            return None                   # province/county not in the geography tables: nothing to attach to
        settlement, _ = CityVillage.objects.get_or_create(
            district=district, name=municipality.city_village,
            defaults={'settlement_type': _settlement_type(municipality), 'population': municipality.population})
    settlement.has_municipality = True
    settlement.municipality = municipality
    if municipality.population:
        settlement.population = municipality.population
    settlement.save()
    municipality.save()                   # picks up the new city_village_fk
    return settlement


def _dehyaris_of_place(municipality, settlement, exclude_user):
    """Dehyari profiles registered for the same place (by link, or by name when the link is missing)."""
    wanted = tuple(norm(getattr(municipality, n)) for n in ('province', 'county', 'city_village'))
    found = []
    for profile in UserProfile.objects.filter(role='dehyari').exclude(user=exclude_user).select_related('user'):
        same_link = settlement is not None and profile.city_village_fk_id == settlement.id
        same_name = (norm(profile.province), norm(profile.county),
                     norm(profile.city_village_name or profile.city_village)) == wanted
        if same_link or same_name:
            found.append(profile)
    return found


@transaction.atomic
def approve(municipality, approved_by):
    """Approve a municipality: add its place if new, hand the dehyari role to its manager.

    An existing dehyari of the same place becomes an ordinary citizen (the new one replaces them).
    Returns the list of replaced users.
    """
    municipality.status = 'active'
    municipality.verified_at = timezone.now()
    municipality.verified_by = approved_by
    municipality.save()

    manager = municipality.admin_user
    settlement = ensure_settlement(municipality)
    replaced = []
    if manager is None:
        return replaced

    for old in _dehyaris_of_place(municipality, settlement, exclude_user=manager):
        old.role = 'citizen'
        old.save(update_fields=['role'])
        replaced.append(old.user)
        Notification.objects.create(
            user=old.user, notification_type='system_update',
            title='پایان مسئولیت دهیار',
            message=f'دهیار جدید برای {municipality.city_village} تأیید شد و حساب شما به شهروند تبدیل شد.')

    profile = manager.profile
    profile.role = 'dehyari'
    profile.is_verified = True
    profile.approval_status = 'approved'
    profile.save()
    manager.is_active = True
    manager.save(update_fields=['is_active'])
    Notification.objects.create(
        user=manager, notification_type='request_status',
        title='شهرداری/دهیاری تایید شد',
        message=f'{municipality.name} تایید شد. اکنون می‌توانید وارد حساب خود شوید.')
    return replaced
