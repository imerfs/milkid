"""IP block list managed from the admin server panel; blocked clients get 403 before any view runs."""
from django.core.cache import cache
from django.http import HttpResponse

from main.ratelimit import client_ip

CACHE_KEY = 'ipblock:set'
CACHE_SECONDS = 60


def blocked_ips():
    from main.models import BlockedIP      # imported lazily: the middleware loads before apps are ready
    ips = cache.get(CACHE_KEY)
    if ips is None:
        ips = set(BlockedIP.objects.values_list('ip', flat=True))
        cache.set(CACHE_KEY, ips, CACHE_SECONDS)
    return ips


def invalidate():
    cache.delete(CACHE_KEY)


class BlockedIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if client_ip(request) in blocked_ips():
            return HttpResponse('Forbidden', status=403, content_type='text/plain; charset=utf-8')
        return self.get_response(request)
