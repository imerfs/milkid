"""Admin-managed redirects and a lightweight page-view counter (server panel "redirects" and "stats" tabs)."""
import logging

from django.core.cache import cache
from django.db import DatabaseError, IntegrityError
from django.db.models import F
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.utils import timezone

logger = logging.getLogger(__name__)
CACHE_KEY = 'siteextras:redirects'
# never redirected and never counted: assets, APIs and the admin area (an admin must not lock themselves out)
SKIP_PREFIXES = ('/static/', '/media/', '/api/', '/dashboard/admin/', '/admin/', '/healthz', '/2fa/')


def redirect_map():
    from main.models import SiteRedirect     # middleware loads before apps are ready
    table = cache.get(CACHE_KEY)
    if table is None:
        table = {r.old_path: (r.new_path, r.permanent) for r in SiteRedirect.objects.all()}
        cache.set(CACHE_KEY, table, 60)
    return table


def invalidate():
    cache.delete(CACHE_KEY)


class RedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(SKIP_PREFIXES):
            hit = redirect_map().get(request.path)
            if hit is not None:
                from main.models import SiteRedirect
                SiteRedirect.objects.filter(old_path=request.path).update(hits=F('hits') + 1)
                new_path, permanent = hit
                return (HttpResponsePermanentRedirect if permanent else HttpResponseRedirect)(new_path)
        return self.get_response(request)


class PageViewMiddleware:
    """Counts successful HTML GETs per day and path. A counting failure never breaks the page."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.method == 'GET' and response.status_code == 200 and not request.path.startswith(SKIP_PREFIXES)
                and response.get('Content-Type', '').startswith('text/html')):
            self.count(request.path[:200])
            self.visit(request)
        return response

    @staticmethod
    def visit(request):
        """One row per page view with the address and device; old rows are pruned now and then. Never breaks the page."""
        import random                                           # pylint: disable=import-outside-toplevel
        from datetime import timedelta                         # pylint: disable=import-outside-toplevel
        from main import devices                               # pylint: disable=import-outside-toplevel
        from main.models import SiteVisit                      # pylint: disable=import-outside-toplevel
        try:
            info = devices.parse(request.META.get('HTTP_USER_AGENT', ''))
            user = getattr(request, 'user', None)
            SiteVisit.objects.create(ip=request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR') or None,
                                     user=user if user is not None and user.is_authenticated else None, path=request.path[:200],
                                     kind=info['kind'], device=info['label'][:120], model_name=info['model'][:80])
            if random.random() < 0.002:
                SiteVisit.objects.filter(at__lt=timezone.now() - timedelta(days=90)).delete()
        except Exception:                                      # pylint: disable=broad-except
            logger.warning('visit not recorded', exc_info=True)

    @staticmethod
    def count(path):
        from main.models import DailyPageView
        day = timezone.localdate()
        try:
            if not DailyPageView.objects.filter(day=day, path=path).update(views=F('views') + 1):
                DailyPageView.objects.create(day=day, path=path, views=1)
        except IntegrityError:          # two workers created the row at once
            DailyPageView.objects.filter(day=day, path=path).update(views=F('views') + 1)
        except DatabaseError:
            logger.warning('page view not counted for %s', path, exc_info=True)
