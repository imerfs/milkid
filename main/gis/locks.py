"""Services are refused for a plot that is locked (debt, a neighbour's complaint, street occupation).

A request names its plot by the renewal code in ``parcel_number`` (شماره پلاک). The code is looked up as typed, with
Persian digits and spaces tolerated. Two plots may share a code in the drawing; if any of them is locked the request
is refused, because it cannot be told which one is meant.
"""
from django.db.models import Exists, OuterRef

from main.accounting.parse import digits
from main.models import MapParcel, ParcelLock


def normalise(code):
    return '-'.join(digits(code).replace('_', ' ').replace('/', ' ').split())


def locked_parcels(code):
    """The locked plots (those with an active lock) whose renewal code is ``code``; empty for anything else."""
    code = normalise(code)
    if not code:
        return []
    active = ParcelLock.objects.filter(parcel=OuterRef('pk'), unlocked_at__isnull=True)
    return list(MapParcel.objects.filter(renewal_code=code).filter(Exists(active)))


def refusal(code):
    """The sentence that tells why services are refused for ``code``, or '' when they are not."""
    parcels = locked_parcels(code)
    if not parcels:
        return ''
    reasons = sorted({lock.get_reason_display() for parcel in parcels for lock in parcel.locks.filter(unlocked_at__isnull=True)})
    return f'ملک با کد نوسازی {normalise(code)} قفل است و از خدمات محروم شده ({"، ".join(reasons)}). برای رفع قفل به دهیاری مراجعه کنید.'
