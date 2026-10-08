from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from main.models import UserProfile

def role_required(allowed_roles):
    """
    Decorator for role-based access control
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('main:login')

            try:
                user_role = request.user.profile.role
                if user_role not in allowed_roles:
                    messages.error(request, 'شما دسترسی لازم برای این صفحه را ندارید.')
                    return redirect('main:dashboard')
            except UserProfile.DoesNotExist:
                messages.error(request, 'پروفایل کاربری یافت نشد.')
                return redirect('main:home')

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
