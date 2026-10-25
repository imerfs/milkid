"""The appointment section of the panels (وقت‌گیری): what each role sees inside its own panel.

A citizen picks a technical expert or a council member, a day and a time. The expert / inspector / council member sees the
requests, decides on them and sets the weekly hours. The same partial (``partials/visits_panel.html``) is shown in every
panel, so nobody is sent to a page with a different look; the actions redirect back to the panel (``panel_url``).
"""
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from main.models import AvailabilityRule
from main.office import appointments as svc
from main.office.directory import identity

# Where each role's appointment section lives: (url name, opens through ?tab=, anchor)
PANELS = {
    'citizen': ('main:owner_dashboard', True, 'visits'), 'owner': ('main:owner_dashboard', True, 'visits'),
    'resident': ('main:owner_dashboard', True, 'visits'),
    'council': ('main:council_dashboard', True, 'visits'),
    'inspector': ('main:inspector_dashboard', True, 'visits'),
    'engineer': ('main:dehyari_expert_dashboard', False, 'visits-section'),
}


def has_visits(user):
    return svc.role_of(user) in PANELS


def panel_url(user, **params):
    """The user's panel opened on the appointment section (the dashboard for roles without one)."""
    spec = PANELS.get(svc.role_of(user))
    if spec is None:
        return reverse('main:dashboard')
    name, by_tab, anchor = spec
    query = {'tab': 'visits'} if by_tab else {}
    query.update({k: v for k, v in params.items() if v})
    return f"{reverse(name)}{'?' + urlencode(query) if query else ''}#{anchor}"


def _hours(user):
    rules = {r.weekday: r for r in AvailabilityRule.objects.filter(provider=user)}
    return [{'index': i, 'name': name, 'rule': rules.get(i)} for i, name in enumerate(svc.WEEKDAYS)]


def _citizen(request, mine):
    user = request.user
    people = svc.providers_for(user).order_by('profile__role', 'last_name')
    with_hours = set(AvailabilityRule.objects.filter(provider__in=people).values_list('provider_id', flat=True))
    raw = request.GET.get('provider', '')
    chosen = None
    cards = []
    for person in people:
        who = identity(person)
        cards.append({'user': person, 'id': person.pk, 'name': who.name, 'title': who.title, 'org': who.org,
                      'has_hours': person.pk in with_hours, 'on': raw == str(person.pk),
                      'href': panel_url(user, provider=person.pk)})
        if raw == str(person.pk):
            chosen = person
    data = {'mode': 'citizen', 'cards': cards, 'chosen': chosen, 'upcoming': mine['upcoming'], 'past': mine['past']}
    if chosen is not None:
        strip = svc.day_strip(chosen)
        # no day asked for: open the first one that still has a free time
        first_free = next((d['date'] for d in strip if d['free']), timezone.localdate())
        date = svc.parse_date(request.GET.get('date'), first_free)
        for day in strip:
            day['href'] = panel_url(user, provider=chosen.pk, date=day['iso'])
            day['on'] = day['date'] == date
        data.update(strip=strip, date_label=svc.jalali_label(date), slots=[s for s, _ in svc.free_slots(chosen, date)],
                    form=request.session.pop('visit_form', None) or {})
    return data


def panel_context(request):
    """``{'visits': {...}}`` for the panel of ``request.user``; the template shows nothing when ``mode`` is missing."""
    user = request.user
    mine = svc.my_appointments(user)
    if mine['is_provider']:
        data = {'mode': 'provider', 'incoming': mine['incoming'], 'incoming_past': mine['incoming_past'],
                'hours': _hours(user), 'pending': sum(1 for a in mine['incoming'] if a.status == 'pending')}
    elif svc.role_of(user) in svc.CLIENT_ROLES:
        data = _citizen(request, mine)
    else:
        data = {}
    data['book_url'] = reverse('main:appointment_book', args=[data['chosen'].pk]) if data.get('chosen') else ''
    return {'visits': data}
