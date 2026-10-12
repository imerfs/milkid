from django import template

from main import seo as seo_data
from main.models import Service

register = template.Library()


@register.inclusion_tag('partials/seo_head.html', takes_context=True)
def service_seo(context, service):
    """Head metadata for a service page: its own description, Service schema, breadcrumb ending in its name."""
    request = context['request']
    crumbs = seo_data.breadcrumbs(request, 'service_detail')
    crumbs[-1] = (service.name, crumbs[-1][1])
    page = dict(context['seo'])
    page['jsonld'] = [seo_data.ld_dumps(seo_data.service_ld(request, service)),
                      seo_data.ld_dumps(seo_data.breadcrumb_ld(crumbs))]
    page['breadcrumbs'] = crumbs
    text = ' '.join(service.description.split())
    return {'seo': page, 'description': text[:155] + ('…' if len(text) > 155 else '')}


@register.simple_tag
def footer_services(limit=4):
    """A few active services for footer links (real pages instead of repeating the catalog URL)."""
    return list(Service.objects.filter(is_active=True)[:limit])


@register.simple_tag
def related_services(service, limit=3):
    """Other active services in the same category, then any others, for internal linking."""
    others = Service.objects.filter(is_active=True).exclude(pk=service.pk)
    same = list(others.filter(category=service.category)[:limit])
    if len(same) < limit:
        same += list(others.exclude(category=service.category)[:limit - len(same)])
    return same
