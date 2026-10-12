"""Dehyari account of a municipality: created inactive at registration, activated on approval.

Registration only *requests* a place. Nothing about existing places or accounts changes until an
admin approves, so a stranger cannot unseat the current dehyari by filling in a form.
"""
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from main.geography import norm
from main.models import CityVillage, District, Municipality, Notification, UserProfile


def create_pending_manager(municipality, data):
    """Create the inactive dehyari account from the registration form data and link it."""
    first, _, last = (data['manager_name'] or '').strip().partition(' ')
    user = User(username=data['manager_username'], email=data.get('manager_email', ''),
                first_name=first, last_name=last, is_active=False)
    user.set_password(data['manager_password'])
    user.save()

    profile = UserProfile.objects.get(user=user)     # created by the post_save signal
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


def dehyaris_of_place(province, county, city_village, settlement_id, exclude_user):
    """Dehyari profiles of the same place (by link, or by name when the link is missing)."""
    wanted = (norm(province), norm(county), norm(city_village))
    found = []
    for profile in UserProfile.objects.filter(role='dehyari').exclude(user=exclude_user).select_related('user'):
        same_link = settlement_id is not None and profile.city_village_fk_id == settlement_id
        same_name = (norm(profile.province), norm(profile.county),
                     norm(profile.city_village_name or profile.city_village)) == wanted
        if same_link or same_name:
            found.append(profile)
    return found


def demote(profiles, place):
    """Turn the given dehyaris into citizens (they are replaced) and tell them."""
    for old in profiles:
        old.role = 'citizen'
        old.save(update_fields=['role'])
        Notification.objects.create(
            user=old.user, notification_type='system_update',
            title='پایان مسئولیت دهیار',
            message=f'دهیار جدید برای {place} تأیید شد و حساب شما به شهروند تبدیل شد.')
    return [p.user for p in profiles]


def make_dehyari(profile):
    """An admin set ``profile`` to dehyari by hand: replace the place's previous dehyari and link its municipality."""
    place = profile.city_village_name or profile.city_village
    if not place:
        return []
    replaced = demote(dehyaris_of_place(profile.province, profile.county, place,
                                        profile.city_village_fk_id, profile.user), place)
    towns = Municipality.objects.filter(status='active')
    town = (towns.filter(city_village_fk_id=profile.city_village_fk_id) if profile.city_village_fk_id
            else towns.filter(city_village=place)).first()
    if town:
        town.admin_user = town.manager_user = profile.user
        town.save(update_fields=['admin_user', 'manager_user'])
    return replaced


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
    if manager is None:
        return []

    replaced = demote(dehyaris_of_place(municipality.province, municipality.county, municipality.city_village,
                                        settlement.id if settlement else None, manager), municipality.city_village)

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
