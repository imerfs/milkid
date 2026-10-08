"""Notification module: one place that creates user notifications."""
from main.models import Notification


def notify(user, title, message, *, request=None, kind='request_status'):
    """Create a notification for ``user`` (optionally tied to a ServiceRequest)."""
    return Notification.objects.create(
        user=user, notification_type=kind, title=title, message=message,
        related_request=request,
    )
