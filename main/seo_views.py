from django.http import HttpResponse
from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_GET

from main.models import Service
from main.seo import DISALLOW, absolute, site


@require_GET
def robots_txt(request):
    lines = ['User-agent: *', 'Allow: /static/']
    lines += [f'Disallow: {path}' for path in DISALLOW]
    lines.append(f'Sitemap: {absolute(request, reverse("sitemap"))}')
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


@require_GET
def llms_txt(request):
    s = site()
    page = lambda name: absolute(request, reverse(f'main:{name}'))
    lines = [
        f'# {s["name"]}',
        '',
        f'> {s["description"]}',
        '',
        '## صفحات اصلی',
        f'- [خانه]({page("home")}): معرفی سامانه و دسترسی سریع به خدمات',
        f'- [خدمات]({page("services_catalog")}): فهرست خدمات دهیاری و شهرداری',
        f'- [بازار املاک]({page("property_marketplace")}): جستجوی املاک',
        f'- [آگهی‌های ملک]({page("property_listings")}): آگهی‌های تأییدشده فروش و اجاره',
        f'- [درباره ما]({page("about")})',
        f'- [تماس با ما]({page("contact")})',
        f'- [ثبت‌نام]({page("register")})',
        '',
        '## خدمات',
    ]
    for service in Service.objects.filter(is_active=True).order_by('category', 'name'):
        url = absolute(request, reverse('main:service_detail', args=[service.slug]))
        lines.append(f'- [{service.name}]({url}): {service.description.strip().splitlines()[0][:120]}'
                     if service.description.strip() else f'- [{service.name}]({url})')
    lines += ['', '## فنی', f'- [Sitemap]({absolute(request, reverse("sitemap"))})', '']
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')


@require_GET
def favicon(request):
    """Browsers request /favicon.ico regardless of <link rel=icon>; send them to the real file."""
    return redirect(static('icons/favicon.ico'), permanent=True)
