"""Citizen panel (owner dashboard): tabs and deep links from the old stand-alone pages."""
from django.shortcuts import redirect
from django.urls import reverse

from main.access import role_of

PANEL_TABS = ('dashboard', 'new-request', 'tracking', 'documents', 'payments', 'messages', 'ads', 'visits', 'inquiry', 'profile')
CITIZEN_ROLES = ('citizen', 'owner', 'resident')


def panel_tab_redirect(request, tab):
    """Send a citizen who opens an old page URL to the same section inside the panel.

    Pages shown inside the panel's own frame (Sec-Fetch-Dest: iframe, or ?embed=1) are left alone.
    """
    if (request.method == 'GET' and request.user.is_authenticated
            and request.headers.get('Sec-Fetch-Dest') != 'iframe' and not request.GET.get('embed')
            and role_of(request.user) in CITIZEN_ROLES):
        return redirect(f"{reverse('main:owner_dashboard')}?tab={tab}")
    return None
