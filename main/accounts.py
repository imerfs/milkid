"""Removing an account keeps everything the person created."""
from django.core.cache import cache
from django.utils import timezone


def soft_delete_user(user):
    """Remove ``user`` from the system without deleting their data.

    Requests, payments, messages, ads and the rest stay in place (they are the office's records);
    the account can no longer log in and is listed only in the admin's "deleted" tab. Its username and
    national ID are released so the same person can register again; the originals are kept on the profile.
    """
    profile = user.profile
    profile.deleted_username = user.username
    profile.deleted_national_id = profile.national_id or ''
    profile.national_id = None
    profile.is_active = False
    profile.deleted_at = timezone.now()
    profile.save(update_fields=['deleted_username', 'deleted_national_id', 'national_id', 'is_active', 'deleted_at'])
    user.username = f'deleted-{user.id}'
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=['username', 'is_active', 'password'])
    cache.delete(f'user_last_seen_{user.id}')
