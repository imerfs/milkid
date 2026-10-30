"""Who is who in the office system: organizations, the identity shown beside every message, and who may write to whom.

An organization is a ``Municipality`` row of any type (dehyari, shahrdari, bakhshdari, farmandari). Staff can write to staff
of any organization (so a dehyari can write to the bakhshdari and back) and to the citizens of their own village. A citizen
writes to the staff of their home village and of the organization they switched to.
"""
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db.models import Case, Q, When

from main import roles
from main.models import Municipality
from main.office.roles import is_admin

STAFF_ROLES = roles.MUNICIPAL_STAFF_ROLES
ORG_TITLES = {'dehyari': 'دهیار', 'shahrdari': 'شهردار', 'bakhshdari': 'بخشدار', 'farmandari': 'فرماندار'}


def _profile(user):
    return getattr(user, 'profile', None)


def village_of(user):
    """Village the user writes from ('' = none, e.g. an admin)."""
    if is_admin(user):
        return ''
    profile = _profile(user)
    if profile is not None and profile.role == 'dehyari':
        municipality = Municipality.objects.filter(admin_user=user).first()
        if municipality:
            return municipality.city_village
    return (profile.city_village or profile.city_village_name or '') if profile is not None else ''


def org_of(user):
    """The organization the user works for or lives in (None for an admin or someone without a village)."""
    if not hasattr(user, '_org_cache'):
        org = Municipality.objects.filter(Q(admin_user=user) | Q(manager_user=user)).first()
        village = village_of(user)
        if org is None and village:
            org = Municipality.objects.filter(city_village=village).order_by(Case(When(status='active', then=0), default=1), 'id').first()
        user._org_cache = org
    return user._org_cache


def effective_org(user):
    """Where a citizen's requests and letters go now: the chosen organization, else the home one."""
    profile = _profile(user)
    chosen = getattr(profile, 'active_municipality', None)
    return chosen or org_of(user)


@dataclass(frozen=True)
class Identity:
    name: str
    title: str          # "دهیار", "کارشناس اداری", "شهروند" ...
    org: str            # "دهیاری بهرنگر" or ""
    initials: str

    @property
    def line(self):
        return f'{self.title} · {self.org}' if self.org else self.title


def _initials(name):
    parts = [p for p in name.replace('‌', ' ').split() if p]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else '')) if parts else '؟'


def identity(user):
    """Name, position and organization of the person behind a message."""
    name = user.get_full_name() or user.username
    profile = _profile(user)
    org = org_of(user) if profile is not None and profile.role != 'admin' else None
    if org is not None and user.pk in (org.admin_user_id, org.manager_user_id):
        title = ORG_TITLES.get(org.municipality_type) or profile.get_role_display()
    else:
        title = profile.get_role_display() if profile is not None else ''
    return Identity(name=name, title=title, org=org.name if org is not None else '', initials=_initials(name))


def allowed_recipients(sender):
    """Active users this sender may write to (letters and chats)."""
    people = User.objects.filter(is_active=True, profile__is_active=True).exclude(pk=sender.pk).select_related('profile')
    if is_admin(sender):
        return people
    home = village_of(sender)
    if sender.profile.role in STAFF_ROLES:
        return people.filter(Q(profile__city_village=home) | Q(profile__role__in=STAFF_ROLES))
    villages = {home}
    chosen = getattr(sender.profile, 'active_municipality', None)
    if chosen is not None:
        villages.add(chosen.city_village)
    return people.filter(profile__role__in=STAFF_ROLES, profile__city_village__in=villages)   # citizens write to offices only


def organizations(user, query=''):
    """Active organizations the user may pick people from (a citizen sees every active one: that is the switcher)."""
    orgs = Municipality.objects.filter(status='active')
    query = (query or '').strip()
    if query:
        orgs = orgs.filter(Q(name__icontains=query) | Q(city_village__icontains=query) | Q(county__icontains=query) |
                           Q(province__icontains=query))
    return orgs.order_by('municipality_type', 'name')[:40]


def people_of(user, org):
    """Staff of ``org`` (and, for its own staff, its citizens) that ``user`` may write to."""
    return allowed_recipients(user).filter(profile__city_village=org.city_village).order_by('profile__role', 'last_name')


def requests_for(village):
    """THE rule for "which requests belong to ``village``" (every list, panel, file and download check goes through it).

    A request addressed to a municipality belongs to that municipality's village and to nobody else's. A request without a target belongs to the village
    it was filed under, or else to the home village of its applicant (profile village, by id or by name).
    """
    return (Q(target_municipality__city_village=village) |
            Q(target_municipality__isnull=True) & (Q(city_village__name=village) | Q(user__profile__city_village=village) |
                                                   Q(user__profile__city_village_name=village)))
