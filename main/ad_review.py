"""Admin review of property advertisements and of edits to them: the one place that approves or rejects.

The admin dashboard form, the property-ads page and the JSON endpoints all call these verbs; each sets the status,
records who decided and when, and tells the advertiser.
"""
from django.utils import timezone

from main.models import Notification


def _tell(user, title, message):
    Notification.objects.create(user=user, notification_type='system_update', title=title, message=message)


def approve_ad(ad, admin, notes=''):
    ad.status = 'approved'
    ad.approved_at = timezone.now()
    ad.approved_by = admin
    ad.admin_notes = notes or 'آگهی توسط مدیر سیستم تایید شد.'
    ad.save()
    _tell(ad.user, 'آگهی ملک شما تایید شد',
          f'آگهی ملک {ad.get_property_type_display()} شما در {ad.city_village or ad.county or "سیستم"} تایید و منتشر شد.')


def reject_ad(ad, admin, notes=''):
    ad.status = 'rejected'
    ad.admin_notes = notes or 'آگهی توسط مدیر رد شد.'
    ad.save()
    _tell(ad.user, 'آگهی ملک شما رد شد',
          f'آگهی ملک {ad.get_property_type_display()} شما رد شد. علت: {ad.admin_notes}')


def approve_edit(edit_log, admin, notes=''):
    """Apply the requested changes to the advertisement. Returns False, leaving the edit pending, if they cannot be applied.

    ``apply_changes`` only works on an approved edit, so the status is set first and put back on failure.
    """
    edit_log.status = 'approved'
    if not edit_log.apply_changes():
        edit_log.status = 'pending'
        return False
    _decide(edit_log, admin, 'approved', notes or 'تغییرات توسط مدیر تایید شد.')
    _tell(edit_log.user, 'درخواست ویرایش آگهی تایید شد',
          f'درخواست ویرایش آگهی {edit_log.advertisement.get_property_type_display()} شما تایید و اعمال شد.')
    return True


def reject_edit(edit_log, admin, notes=''):
    _decide(edit_log, admin, 'rejected', notes or 'درخواست ویرایش توسط مدیر رد شد.')
    _tell(edit_log.user, 'درخواست ویرایش آگهی رد شد',
          f'درخواست ویرایش آگهی {edit_log.advertisement.get_property_type_display()} شما رد شد.')


def _decide(edit_log, admin, status, notes):
    edit_log.status = status
    edit_log.reviewed_by = admin
    edit_log.reviewed_at = timezone.now()
    edit_log.admin_notes = notes
    edit_log.save()
