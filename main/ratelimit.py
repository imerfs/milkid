"""Brute-force / spam throttling for unauthenticated POST endpoints."""
from django.core.cache import cache
from django.http import HttpResponse

# path prefix -> (max POSTs, window in seconds), counted per client IP
LIMITS = {
    '/login/': (10, 300),
    '/register': (10, 3600),
    '/contact/': (5, 600),
}


def client_ip(request):
    """Real client IP. nginx sets X-Real-IP from the socket peer; the left-most
    X-Forwarded-For entry is client-controlled and must not be trusted."""
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')


class AuthThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST':
            for prefix, (limit, window) in LIMITS.items():
                if request.path.startswith(prefix):
                    key = f'throttle:{prefix}:{client_ip(request)}'
                    cache.add(key, 0, window)
                    try:
                        count = cache.incr(key)
                    except ValueError:
                        cache.set(key, 1, window)
                        count = 1
                    if count > limit:
                        return HttpResponse('Too many requests. Try again later.', status=429,
                                            content_type='text/plain; charset=utf-8')
                    break
        return self.get_response(request)
