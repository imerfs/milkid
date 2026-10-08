"""
Custom middleware for MelkID application
"""
import logging
import time
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.conf import settings

logger = logging.getLogger('main')


class ErrorHandlingMiddleware:
    """
    Middleware to handle errors gracefully and log them
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        """
        Handle exceptions and return appropriate response
        """
        # 404 / 403 / 400 are normal outcomes: let Django answer them with
        # their proper status codes instead of turning them into a 500.
        if isinstance(exception, (Http404, PermissionDenied, SuspiciousOperation)):
            return None

        logger.error(
            f'Exception in request: {request.path}',
            exc_info=True,
            extra={
                'request': request,
                'user': request.user if hasattr(request, 'user') else None,
            }
        )

        # نکته: request.is_ajax() در Django 4.0 حذف شد؛ جایگزین مدرن آن:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
            return JsonResponse({
                'error': True,
                'message': 'خطایی در پردازش درخواست رخ داده است.',
                'detail': str(exception) if settings.DEBUG else None
            }, status=500)

        return render(request, '500.html', {
            'exception': exception if settings.DEBUG else None
        }, status=500)


class PerformanceMonitoringMiddleware:
    """
    Middleware to monitor request performance
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration = time.time() - start_time
        
        # Log slow requests (> 1 second)
        if duration > 1.0:
            logger.warning(
                f'Slow request: {request.path} took {duration:.2f}s',
                extra={
                    'duration': duration,
                    'path': request.path,
                    'method': request.method,
                    'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous'
                }
            )
        
        # Add performance header
        response['X-Response-Time'] = f'{duration:.3f}s'
        
        return response


class SecurityHeadersMiddleware:
    """
    Add security headers to responses
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add security headers
        if not settings.DEBUG:
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response


class RequestLoggingMiddleware:
    """
    Log all requests for security monitoring
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.security_logger = logging.getLogger('django.security')

    def __call__(self, request):
        # Log security-relevant requests
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            self.security_logger.info(
                f'{request.method} {request.path}',
                extra={
                    'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous',
                    'ip': self.get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                }
            )
        
        response = self.get_response(request)
        
        # Log failed authentication attempts
        if response.status_code == 403:
            self.security_logger.warning(
                f'Access denied: {request.path}',
                extra={
                    'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous',
                    'ip': self.get_client_ip(request),
                }
            )
        
        return response

    @staticmethod
    def get_client_ip(request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ActiveUserMiddleware:
    """
    Middleware to monitor active users and manage real-time online status.
    - Sets cache heartbeat for authenticated users (5 minutes TTL).
    - Immediately logs out blocked / suspended users attempting access.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow access-blocked and static assets without interruption
        if request.path.startswith('/access-blocked/') or request.path.startswith('/logout/'):
            return self.get_response(request)

        # Check if the user session belongs to a blocked/inactive user
        session_user_id = request.session.get('_auth_user_id')
        if session_user_id:
            from django.contrib.auth.models import User
            from django.contrib.auth import logout
            from django.shortcuts import redirect
            from django.core.cache import cache

            try:
                user_obj = User.objects.select_related('profile').get(id=session_user_id)
                user_blocked = not user_obj.is_active
                if hasattr(user_obj, 'profile') and not user_obj.profile.is_active:
                    user_blocked = True

                if user_blocked:
                    cache.delete(f'user_last_seen_{session_user_id}')
                    logout(request)
                    return redirect('main:access_blocked')
            except User.DoesNotExist:
                pass

        if hasattr(request, 'user') and request.user.is_authenticated:
            # User is active: update last seen in cache
            from django.core.cache import cache
            from django.utils import timezone
            cache.set(f'user_last_seen_{request.user.id}', timezone.now().isoformat(), 300)

        response = self.get_response(request)
        return response

