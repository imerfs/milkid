"""The citizen's property inquiry map («استعلام خرید ملک»): a light map of a village's plots and a search by renewal code or plot number."""
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from main.access import policy_required
from main.gis import inquiry
from main.models import MapParcel, VillageMap
from main.ratelimit import client_ip

LIMITS = {'data': (40, 3600), 'search': (240, 3600), 'parcel': (400, 3600)}


def _throttled(request, name):
    """A signed-in user may not pull the whole village map or run searches without end: a per-user, per-hour budget for each endpoint."""
    limit, window = LIMITS[name]
    key = f'inquiry:{name}:{request.user.pk}:{client_ip(request)}'
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > limit


def _map(slug):
    village_map = VillageMap.objects.filter(slug=slug).first()
    if village_map is None:
        raise Http404('نقشه پیدا نشد.')
    return village_map


def _json(payload, status=200):
    response = JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False, 'separators': (',', ':')})
    response['Cache-Control'] = 'private, no-store'
    return response


@policy_required('inquiry.view')
def inquiry_page(request, slug=None):
    maps = list(VillageMap.objects.order_by('name'))
    if not maps:
        return render(request, 'main/inquiry/map.html', {'maps': [], 'config': None})
    chosen = next((m for m in maps if m.slug == slug), None)
    if chosen is None:                                               # the citizen's own village first
        village = getattr(request.user.profile, 'city_village', '') or ''
        chosen = next((m for m in maps if m.name == village), maps[0])
    config = {
        'slug': chosen.slug, 'name': chosen.name, 'disclaimer': inquiry.DISCLAIMER,
        'basemap': next((b for b in settings.GIS_BASEMAPS if b['id'] == 'carto'), None),
        'urls': {'data': reverse('main:inquiry_data', args=[chosen.slug]), 'search': reverse('main:inquiry_search', args=[chosen.slug]),
                 'parcel': reverse('main:inquiry_parcel', args=[chosen.slug, 0])},
    }
    return render(request, 'main/inquiry/map.html', {'maps': maps, 'chosen': chosen, 'config': config, 'embed': bool(request.GET.get('embed'))})


@require_GET
@policy_required('inquiry.view', api=True)
def inquiry_data(request, slug):
    if _throttled(request, 'data'):
        return HttpResponse('Too many requests. Try again later.', status=429, content_type='text/plain; charset=utf-8')
    return _json(inquiry.collection(_map(slug)))


@require_GET
@policy_required('inquiry.view', api=True)
def inquiry_search(request, slug):
    if _throttled(request, 'search'):
        return HttpResponse('Too many requests. Try again later.', status=429, content_type='text/plain; charset=utf-8')
    return _json({'results': inquiry.search(_map(slug), request.GET.get('q', ''))})


@require_GET
@policy_required('inquiry.view', api=True)
def inquiry_parcel(request, slug, parcel_id):
    if _throttled(request, 'parcel'):
        return HttpResponse('Too many requests. Try again later.', status=429, content_type='text/plain; charset=utf-8')
    village_map = _map(slug)
    parcel = MapParcel.objects.select_related('land_use').filter(village_map=village_map, pk=parcel_id).first()
    if parcel is None:
        raise Http404('قطعه پیدا نشد.')
    return _json({'parcel': inquiry.card(parcel, inquiry._zone_names(village_map))})       # pylint: disable=protected-access
