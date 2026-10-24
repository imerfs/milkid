"""Village web-GIS: the map page for the village's technical expert, and the JSON behind its side panel.

Access: ``gis.view`` / ``gis.edit`` (role engineer; admins always) AND the user belongs to the map's village
(main/gis/access.py). Everything an archive holds is only ever returned to those users.
"""
import json

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from main.access import policy_required
from main.accounting.parse import digits, jalali_str, parse_amount, parse_jalali
from main.gis import data as gis_data, rules
from main.gis.access import may_use
from main.models import MapEasement, MapParcel, ParcelArchive, ParcelFeePayment, ParcelLock, VillageMap
from main.office.errors import Invalid

ARCHIVE_TEXT = ('permit_number', 'permit_type', 'permit_notes', 'owner_name', 'owner_phone', 'building_owner_name',
                'building_owner_phone', 'notes')
NATIONAL_IDS = ('owner_national_id', 'building_owner_national_id')


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
    years = list(range(gis_data.FIRST_YEAR, gis_data.current_year() + 1))
    config = {
        'slug': village_map.slug,
        'csrf': get_token(request),
        'canEdit': may_use(request.user, village_map, 'gis.edit'),
        'canLock': may_use(request.user, village_map, 'gis.lock'),
        'basemaps': settings.GIS_BASEMAPS,
        'waybackConfig': settings.GIS_WAYBACK_CONFIG_URL,
        'trafficUrl': settings.GIS_TRAFFIC_TILE_URL,
        'years': years,
        'urls': {
            'data': reverse('main:gis_data', args=[village_map.slug]),
            'buildings': reverse('main:gis_buildings', args=[village_map.slug]),
            'easements': reverse('main:gis_easements', args=[village_map.slug]),
            'context': reverse('main:gis_context', args=[village_map.slug]) + gis_data.version_query(village_map, 'context'),
            'cad': reverse('main:gis_cad', args=[village_map.slug]) + gis_data.version_query(village_map, 'cad'),
            'parcel': reverse('main:gis_parcel', args=[village_map.slug, 0]),
        },
        'lockReasons': dict(ParcelLock.REASONS),
        'easementKinds': {kind: rules.label(kind) for kind, _ in MapEasement.KINDS},
        'easementRules': {kind: rules.rule(kind) for kind, _ in MapEasement.KINDS},
    }
    return render(request, 'main/gis/village_map.html', {
        'village_map': village_map, 'config': config, 'basemaps': settings.GIS_BASEMAPS,
        'traffic_url': settings.GIS_TRAFFIC_TILE_URL,
        'easement_kinds': [(kind, rules.label(kind), rules.rule(kind)) for kind, _ in MapEasement.KINDS],
        'lock_reasons': ParcelLock.REASONS, 'years': years,
    })


@require_GET
@policy_required('gis.view', api=True)
def map_data(request, slug):
    """Plots, blocks, neighbourhoods and land-use classes as GeoJSON; buildings and easements come separately."""
    village_map = _map_or_none(request, slug)
    if village_map is None:
        return _denied()
    response = HttpResponse(gis_data.dumps(gis_data.map_collection(village_map)), content_type='application/json')
    response['Cache-Control'] = 'private, no-store'
    return response


def _layer(request, slug, features):
    village_map = _map_or_none(request, slug)
    if village_map is None:
        return _denied()
    response = HttpResponse(gis_data.dumps({'type': 'FeatureCollection', 'features': features(village_map)}),
                            content_type='application/json')
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
@policy_required('gis.view', api=True)
def map_buildings(request, slug):
    return _layer(request, slug, gis_data.static_buildings)


@require_GET
@policy_required('gis.view', api=True)
def map_easements(request, slug):
    return _layer(request, slug, gis_data.static_easements)


@require_GET
@policy_required('gis.view', api=True)
def map_cad(request, slug):
    """The cartographic base layer: the plan with its own colours, hatches and texts."""
    village_map = _map_or_none(request, slug)
    if village_map is None:
        return _denied()
    text = gis_data.static_cad(village_map)
    if text is None:
        return JsonResponse({'items': [], 'layers': []})
    response = HttpResponse(text, content_type='application/json')
    response['Cache-Control'] = 'private, max-age=600'
    return response


@require_GET
@policy_required('gis.view', api=True)
def map_context(request, slug):
    """Roads, water, power, trees, limits and street names (the plan's surroundings of the plots)."""
    return _layer(request, slug, gis_data.static_context)


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
        'building_owner_name': archive.building_owner_name if archive else '',
        'building_owner_national_id': archive.building_owner_national_id if archive else '',
        'building_owner_phone': archive.building_owner_phone if archive else '',
        'building_floors': archive.building_floors if archive and archive.building_floors else '',
        'building_floor_area': archive.building_floor_area if archive and archive.building_floor_area else '',
        'notes': archive.notes if archive else '',
        'updated_at': jalali_str(archive.updated_at.date()) if archive else '',
    }


def _payment_dict(payment):
    return {'id': payment.pk, 'fee_type': payment.fee_type, 'fiscal_year': payment.fiscal_year or '',
            'amount': int(payment.amount), 'paid_on': jalali_str(payment.paid_on), 'receipt_no': payment.receipt_no,
            'notes': payment.notes}


def _lock_dict(lock):
    who = lock.locked_by
    return {'id': lock.pk, 'reason': lock.reason, 'reason_label': lock.get_reason_display(), 'notes': lock.notes,
            'locked_at': jalali_str(timezone.localtime(lock.locked_at).date()),
            'locked_by': (who.get_full_name() or who.username) if who else '',
            'active': lock.active,
            'unlocked_at': jalali_str(timezone.localtime(lock.unlocked_at).date()) if lock.unlocked_at else '',
            'unlock_notes': lock.unlock_notes}


def _parcel_dict(parcel):
    payments = list(parcel.payments.all())
    locks = [_lock_dict(lock) for lock in parcel.locks.select_related('locked_by')]
    land_use = parcel.land_use
    return {
        'id': parcel.pk, 'code': parcel.renewal_code, 'block': parcel.block_no, 'number': parcel.number,
        'zone': parcel.zone, 'guild': parcel.guild_no, 'apartment': parcel.apartment_no,
        'kind': parcel.kind, 'area': round(parcel.area_m2, 1), 'building_area': round(parcel.building_area_m2, 1),
        'building_count': parcel.building_count, 'duplicate': parcel.duplicate_code,
        'other_numbers': parcel.other_numbers,
        'land_use': {'name': land_use.name, 'color': land_use.color} if land_use else None,
        'easements': [{'kind': h['k'], 'label': rules.label(h['k']), 'rule': rules.rule(h['k']), 'amount': h['a'],
                       'line': h.get('line', False)} for h in parcel.easement_hits],
        'lot_no': parcel.lot_no, 'permit_in_drawing': parcel.permit_in_drawing,
        'archive': _archive_dict(parcel),
        'payments': [_payment_dict(p) for p in payments],
        'payments_total': int(sum(p.amount for p in payments)),
        'locks': locks, 'locked': any(lock['active'] for lock in locks),
    }


def _parcel(request, slug, parcel_id, action):
    village_map = _map_or_none(request, slug, action)
    if village_map is None:
        return None
    return get_object_or_404(MapParcel.objects.select_related('archive', 'land_use'), pk=parcel_id, village_map=village_map)


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
        for key in NATIONAL_IDS:
            national_id = digits(data.get(key, ''))
            if national_id and not (national_id.isdigit() and len(national_id) == 10):
                raise Invalid('کد ملی باید ۱۰ رقم باشد.')
            values[key] = national_id
        for key in ('owner_phone', 'building_owner_phone'):
            phone = digits(values[key])
            if phone and not phone.isdigit():
                raise Invalid('تلفن باید فقط رقم باشد.')
            values[key] = phone
        floors = digits(data.get('building_floors', ''))
        if floors and not (floors.isdigit() and 0 < int(floors) <= 100):
            raise Invalid('تعداد طبقات را به عدد وارد کنید.')
        values['building_floors'] = int(floors) if floors else None
        floor_area = digits(data.get('building_floor_area', '')).replace(',', '')
        try:
            values['building_floor_area'] = float(floor_area) if floor_area else None
        except ValueError:
            raise Invalid('زیربنا را به عدد وارد کنید.')
        if values['building_floor_area'] is not None and not 0 < values['building_floor_area'] < 1_000_000:
            raise Invalid('زیربنا نامعتبر است.')
        raw_date = str(data.get('permit_date', '')).strip()
        values['permit_date'] = parse_jalali(raw_date) if raw_date else None
        for key, limit in (('permit_number', 60), ('permit_type', 60), ('owner_name', 150), ('building_owner_name', 150)):
            if len(values[key]) > limit:
                raise Invalid('متن وارد شده بیش از حد طولانی است.')
    except Invalid as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    with transaction.atomic():
        ParcelArchive.objects.update_or_create(parcel=parcel, defaults={**values, 'updated_by': request.user})
    parcel = MapParcel.objects.select_related('archive', 'land_use').get(pk=parcel.pk)
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
    parcel = MapParcel.objects.select_related('archive', 'land_use').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})


@require_POST
@policy_required('gis.edit', api=True)
def payment_delete(request, slug, parcel_id, payment_id):
    parcel = _parcel(request, slug, parcel_id, 'gis.edit')
    if parcel is None:
        return _denied()
    get_object_or_404(ParcelFeePayment, pk=payment_id, parcel=parcel).delete()
    parcel = MapParcel.objects.select_related('archive', 'land_use').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})


@require_POST
@policy_required('gis.lock', api=True)
def parcel_lock(request, slug, parcel_id):
    """Lock the plot out of municipal services (debt, a neighbour's complaint, street occupation)."""
    parcel = _parcel(request, slug, parcel_id, 'gis.lock')
    if parcel is None:
        return _denied()
    try:
        data = _body(request)
        reason = str(data.get('reason', ''))
        if reason not in dict(ParcelLock.REASONS):
            raise Invalid('دلیل قفل را انتخاب کنید.')
        notes = str(data.get('notes', '')).strip()[:500]
        if parcel.locks.filter(reason=reason, unlocked_at__isnull=True).exists():
            raise Invalid('این ملک به همین دلیل از قبل قفل است.')
    except Invalid as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    ParcelLock.objects.create(parcel=parcel, reason=reason, notes=notes, locked_by=request.user)
    parcel = MapParcel.objects.select_related('archive', 'land_use').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})


@require_POST
@policy_required('gis.lock', api=True)
def parcel_unlock(request, slug, parcel_id, lock_id):
    parcel = _parcel(request, slug, parcel_id, 'gis.lock')
    if parcel is None:
        return _denied()
    lock = get_object_or_404(ParcelLock, pk=lock_id, parcel=parcel, unlocked_at__isnull=True)
    try:
        notes = str(_body(request).get('notes', '')).strip()[:500]
        if not notes:
            raise Invalid('دلیل رفع قفل را بنویسید.')
    except Invalid as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    lock.unlocked_at, lock.unlocked_by, lock.unlock_notes = timezone.now(), request.user, notes
    lock.save(update_fields=['unlocked_at', 'unlocked_by', 'unlock_notes'])
    parcel = MapParcel.objects.select_related('archive', 'land_use').get(pk=parcel.pk)
    return JsonResponse({'success': True, 'parcel': _parcel_dict(parcel)})
