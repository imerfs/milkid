"""Village web-GIS: the map page for the village's technical expert, and the JSON behind its side panel.

Access: ``gis.view`` / ``gis.edit`` (role engineer; admins always) AND the user belongs to the map's village
(main/gis/access.py). Everything an archive holds is only ever returned to those users.
"""
import json

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from main.access import policy_required
from main.accounting.parse import digits, jalali_str, parse_amount, parse_jalali
from main.gis.access import may_use
from main.models import MapParcel, ParcelArchive, ParcelFeePayment, VillageMap
from main.office.errors import Invalid

ARCHIVE_TEXT = ('permit_number', 'permit_type', 'permit_notes', 'owner_name', 'owner_phone', 'notes')


def _map_or_none(request, slug, action='gis.view'):
    village_map = get_object_or_404(VillageMap, slug=slug)
    return village_map if may_use(request.user, village_map, action) else None


def _denied():
    return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)


def _body(request):
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        raise Invalid('درخواست نامعتبر است.')
    if not isinstance(data, dict):
        raise Invalid('درخواست نامعتبر است.')
    return data


@policy_required('gis.view')
def map_page(request, slug):
    village_map = _map_or_none(request, slug)
    if village_map is None:
        messages.error(request, 'شما به نقشه‌ی این روستا دسترسی ندارید.')
        return redirect('main:home')
    return render(request, 'main/gis/village_map.html', {
        'village_map': village_map,
        'can_edit': may_use(request.user, village_map, 'gis.edit'),
    })


@require_GET
@policy_required('gis.view', api=True)
def map_data(request, slug):
    """Blocks and plots as one GeoJSON FeatureCollection; plots carry only what the map needs to colour them."""
    village_map = _map_or_none(request, slug)
    if village_map is None:
        return _denied()
    archived = set(ParcelArchive.objects.filter(parcel__village_map=village_map).values_list('parcel_id', flat=True))
    paid = set(ParcelFeePayment.objects.filter(parcel__village_map=village_map).values_list('parcel_id', flat=True))
    features = [{
        'type': 'Feature',
        'properties': {'t': 'b', 'n': b.number, 'c': b.parcel_count},
        'geometry': b.geometry,
    } for b in village_map.blocks.all()]
    for p in village_map.parcels.only('id', 'block_no', 'number', 'renewal_code', 'kind', 'area_m2', 'geometry'):
        features.append({
            'type': 'Feature',
            'properties': {'t': 'p', 'id': p.pk, 'code': p.renewal_code, 'b': p.block_no, 'n': p.number,
                           'e': p.kind == 'estimated', 'a': round(p.area_m2), 'f': p.pk in archived,
                           'p': p.pk in paid},
            'geometry': p.geometry,
        })
    response = JsonResponse({'type': 'FeatureCollection', 'features': features,
                             'centre': [village_map.centre_lat, village_map.centre_lng]})
    response['Cache-Control'] = 'private, no-store'
    return response


def _archive_dict(parcel):
    archive = getattr(parcel, 'archive', None)
    return {
        'permit_number': archive.permit_number if archive else '',
        'permit_date': jalali_str(archive.permit_date) if archive else '',
        'permit_type': archive.permit_type if archive else '',
        'permit_notes': archive.permit_notes if archive else '',
        'owner_name': archive.owner_name if archive else '',
        'owner_national_id': archive.owner_national_id if archive else '',
        'owner_phone': archive.owner_phone if archive else '',
        'notes': archive.notes if archive else '',
        'updated_at': jalali_str(archive.updated_at.date()) if archive else '',
    }


def _payment_dict(payment):
    return {'id': payment.pk, 'fee_type': payment.fee_type, 'fiscal_year': payment.fiscal_year or '',
            'amount': int(payment.amount), 'paid_on': jalali_str(payment.paid_on), 'receipt_no': payment.receipt_no,
            'notes': payment.notes}


def _parcel_dict(parcel):
    payments = list(parcel.payments.all())
    return {
        'id': parcel.pk, 'code': parcel.renewal_code, 'block': parcel.block_no, 'number': parcel.number,
        'kind': parcel.kind, 'area': round(parcel.area_m2, 1), 'duplicate': parcel.duplicate_code,
        'other_numbers': parcel.other_numbers, 'archive': _archive_dict(parcel),
        'payments': [_payment_dict(p) for p in payments],
        'payments_total': int(sum(p.amount for p in payments)),
    }


def _parcel(request, slug, parcel_id, action):
    village_map = _map_or_none(request, slug, action)
    if village_map is None:
        return None
    return get_object_or_404(MapParcel.objects.select_related('archive'), pk=parcel_id, village_map=village_map)


@require_GET
@policy_required('gis.view', api=True)
def parcel_detail(request, slug, parcel_id):
    parcel = _parcel(request, slug, parcel_id, 'gis.view')
    if parcel is None:
        return _denied()
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})


@require_POST
@policy_required('gis.edit', api=True)
def parcel_archive_save(request, slug, parcel_id):
    parcel = _parcel(request, slug, parcel_id, 'gis.edit')
    if parcel is None:
        return _denied()
    try:
        data = _body(request)
        values = {key: str(data.get(key, '')).strip() for key in ARCHIVE_TEXT}
        national_id = digits(data.get('owner_national_id', ''))
        if national_id and not (national_id.isdigit() and len(national_id) == 10):
            raise Invalid('کد ملی مالک باید ۱۰ رقم باشد.')
        phone = digits(values['owner_phone'])
        if phone and not phone.isdigit():
            raise Invalid('تلفن مالک باید فقط رقم باشد.')
        values['owner_phone'] = phone
        values['owner_national_id'] = national_id
        raw_date = str(data.get('permit_date', '')).strip()
        values['permit_date'] = parse_jalali(raw_date) if raw_date else None
        for key, limit in (('permit_number', 60), ('permit_type', 60), ('owner_name', 150)):
            if len(values[key]) > limit:
                raise Invalid('متن وارد شده بیش از حد طولانی است.')
    except Invalid as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    with transaction.atomic():
        ParcelArchive.objects.update_or_create(parcel=parcel, defaults={**values, 'updated_by': request.user})
    parcel = MapParcel.objects.select_related('archive').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})


@require_POST
@policy_required('gis.edit', api=True)
def payment_add(request, slug, parcel_id):
    parcel = _parcel(request, slug, parcel_id, 'gis.edit')
    if parcel is None:
        return _denied()
    try:
        data = _body(request)
        fee_type = str(data.get('fee_type', '')).strip()
        if not fee_type:
            raise Invalid('نوع عوارض را وارد کنید.')
        amount = parse_amount(data.get('amount', ''))
        if amount <= 0:
            raise Invalid('مبلغ باید بیشتر از صفر باشد.')
        raw_date = str(data.get('paid_on', '')).strip()
        year = digits(data.get('fiscal_year', ''))
        if year and not (year.isdigit() and 1300 <= int(year) <= 1500):
            raise Invalid('سال را به شمسی وارد کنید، مثل ۱۴۰۴.')
        ParcelFeePayment.objects.create(
            parcel=parcel, fee_type=fee_type[:80], amount=amount, fiscal_year=int(year) if year else None,
            paid_on=parse_jalali(raw_date) if raw_date else None, receipt_no=str(data.get('receipt_no', '')).strip()[:60],
            notes=str(data.get('notes', '')).strip()[:300], created_by=request.user)
    except Invalid as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    parcel = MapParcel.objects.select_related('archive').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})


@require_POST
@policy_required('gis.edit', api=True)
def payment_delete(request, slug, parcel_id, payment_id):
    parcel = _parcel(request, slug, parcel_id, 'gis.edit')
    if parcel is None:
        return _denied()
    get_object_or_404(ParcelFeePayment, pk=payment_id, parcel=parcel).delete()
    parcel = MapParcel.objects.select_related('archive').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})
