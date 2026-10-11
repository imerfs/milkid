"""Removing an account keeps everything the person created."""
from django.core.cache import cache
from django.utils import timezone


def soft_delete_user(user):
    """Remove ``user`` from the system without deleting their data.

    Requests, payments, messages, ads and the rest stay in place (they are the office's records);
    the account can no longer log in and is hidden from the admin lists.
    """
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=['is_active', 'password'])
    profile = user.profile
    profile.is_active = False
    profile.deleted_at = timezone.now()
    profile.save(update_fields=['is_active', 'deleted_at'])
    cache.delete(f'user_last_seen_{user.id}')
