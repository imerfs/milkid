"""SEO data in one place: which pages are public, their descriptions, breadcrumbs and robots rules.

Anything not listed in PAGES is treated as a private page (noindex, never in the sitemap).
"""
import json

from django.conf import settings
from django.urls import reverse

# url_name -> metadata. ``sitemap`` pages are listed in sitemap.xml as static entries.
PAGES = {
    'home': dict(
        label='خانه', sitemap=True, changefreq='daily', priority=1.0,
        description='ملک آیدی؛ سامانه دیجیتال خدمات دهیاری و املاک روستایی: صدور پروانه ساختمان، تأیید سکونت، سند، آگهی املاک و پیگیری آنلاین درخواست‌ها.'),
    'about': dict(
        label='درباره ما', parent='home', sitemap=True, changefreq='monthly', priority=0.5,
        description='درباره ملک آیدی؛ سامانه جامع خدمات شهری و روستایی برای شهروندان، مالکان، دهیاری‌ها و شوراهای روستا.'),
    'contact': dict(
        label='تماس با ما', parent='home', sitemap=True, changefreq='monthly', priority=0.5,
        description='راه‌های تماس با پشتیبانی ملک آیدی؛ ارسال پیام، پیشنهاد و پیگیری مشکلات خدمات دهیاری و املاک.'),
    'services_catalog': dict(
        label='خدمات', parent='home', sitemap=True, changefreq='weekly', priority=0.9,
        description='فهرست خدمات دهیاری و شهرداری: پروانه ساختمان، تغییر کاربری، الحاق به طرح هادی، تأیید سکونت و صدور سند؛ ثبت و پیگیری آنلاین.'),
    'service_detail': dict(
        label='جزئیات خدمت', parent='services_catalog',
        description='شرح خدمت، مدارک مورد نیاز و مدت زمان تخمینی انجام در ملک آیدی.'),
    'property_marketplace': dict(
        label='بازار املاک', parent='home', sitemap=True, changefreq='daily', priority=0.8,
        description='جستجوی املاک روستایی و شهری؛ مشاهده آگهی‌های فروش و اجاره زمین، خانه و باغ با اطلاعات تأییدشده.'),
    'property_listings': dict(
        label='آگهی‌های ملک', parent='property_marketplace', sitemap=True, changefreq='daily', priority=0.8,
        description='آگهی‌های تأییدشده املاک؛ فروش و اجاره ملک مسکونی، تجاری، زمین و کشاورزی در روستاها و شهرها.'),
    'property_detail': dict(
        label='جزئیات آگهی', parent='property_marketplace',
        description='مشخصات کامل آگهی ملک شامل مساحت، موقعیت، قیمت و راه تماس.'),
    'login': dict(
        label='ورود', parent='home', sitemap=True, changefreq='yearly', priority=0.3,
        description='ورود به حساب کاربری ملک آیدی برای ثبت و پیگیری درخواست‌های دهیاری و املاک.'),
    'register': dict(
        label='ثبت‌نام', parent='home', sitemap=True, changefreq='yearly', priority=0.4,
        description='ثبت‌نام در ملک آیدی؛ انتخاب نوع حساب شهروند، مالک، دهیار، کارشناس، ناظر، مسئول مالی یا عضو شورا.'),
    'register_citizen': dict(
        label='ثبت‌نام شهروند', parent='register', sitemap=True, changefreq='yearly', priority=0.4,
        description='ثبت‌نام شهروند و مالک در ملک آیدی برای استفاده از خدمات آنلاین دهیاری و املاک.'),
    'register_municipality': dict(
        label='ثبت‌نام دهیاری', parent='register', sitemap=True, changefreq='yearly', priority=0.4,
        description='ثبت‌نام دهیاری یا شهرداری در ملک آیدی و دریافت پنل مدیریت درخواست‌ها.'),
    'staff_registration_info': dict(
        label='راهنمای ثبت‌نام کارکنان', parent='register', sitemap=True, changefreq='yearly', priority=0.3,
        description='راهنمای ثبت‌نام کارکنان دهیاری، کارشناسان، ناظران فنی و اعضای شورا در ملک آیدی.'),
}

# Paths crawlers must not fetch (prefix match). Public pages are deliberately absent.
DISALLOW = [
    '/healthz/', '/admin/', '/api/', '/dashboard/', '/mayor/', '/council/', '/technical/', '/autocad/',
    '/messaging/', '/payments/', '/profile/', '/notifications/', '/requests/', '/analytics/',
    '/manage-', '/my-', '/edit-property-ad/', '/view-property-ad/', '/update-request-status/',
    '/pending-verification/', '/access-blocked/', '/logout/', '/test', '/construction-permit/',
    '/services/*/wizard/', '/municipality-history/', '/report-violation/', '/ai-fraud-detection/',
]


def site():
    return dict(
        name=settings.SITE_NAME,
        description=settings.SITE_DESCRIPTION,
        url=settings.SITE_URL.rstrip('/'),
        email=settings.SITE_EMAIL,
        phone=settings.SITE_PHONE,
        locality=settings.SITE_ADDRESS_LOCALITY,
        street=settings.SITE_ADDRESS_STREET,
    )


def base_url(request):
    return site()['url'] or f'{request.scheme}://{request.get_host()}'


def absolute(request, path):
    return base_url(request) + path


def breadcrumbs(request, url_name):
    """[(label, absolute_url)] from the first ancestor to the current page; empty for home and private pages."""
    if url_name not in PAGES or url_name == 'home':
        return []
    chain, name = [], url_name
    while name:
        meta = PAGES[name]
        # parents are always static pages; the current page uses the real request path
        path = request.path if name == url_name else reverse(f'main:{name}')
        chain.append((meta['label'], absolute(request, path)))
        name = meta.get('parent')
    return chain[::-1]


def ld_dumps(data):
    """JSON for a <script type=application/ld+json> block; '<' escaped so it cannot close the tag."""
    return json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')


def organization(request):
    s = site()
    url = base_url(request)
    org = {
        '@context': 'https://schema.org',
        '@type': 'LocalBusiness',
        '@id': url + '/#organization',
        'name': s['name'],
        'description': s['description'],
        'url': url + '/',
        'logo': url + '/static/icons/icon-512x512.png',
        'image': url + '/static/icons/og-image.png',
        'areaServed': {'@type': 'Country', 'name': 'ایران'},
        'address': {'@type': 'PostalAddress', 'addressCountry': 'IR'},
    }
    if s['locality']:
        org['address']['addressLocality'] = s['locality']
    if s['street']:
        org['address']['streetAddress'] = s['street']
    if s['email']:
        org['email'] = s['email']
    if s['phone']:
        org['telephone'] = s['phone']
    return org


def website(request):
    s = site()
    url = base_url(request)
    return {
        '@context': 'https://schema.org', '@type': 'WebSite', '@id': url + '/#website',
        'name': s['name'], 'url': url + '/', 'inLanguage': 'fa-IR',
        'publisher': {'@id': url + '/#organization'},
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {'@type': 'EntryPoint',
                       'urlTemplate': absolute(request, reverse('main:property_listings')) + '?q={search_term_string}'},
            'query-input': 'required name=search_term_string',
        },
    }


def breadcrumb_ld(crumbs):
    return {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': i, 'name': label, 'item': url}
            for i, (label, url) in enumerate(crumbs, 1)
        ],
    }


def service_ld(request, service):
    return {
        '@context': 'https://schema.org', '@type': 'Service',
        'name': service.name, 'description': service.description,
        'url': absolute(request, reverse('main:service_detail', args=[service.slug])),
        'serviceType': service.get_category_display(),
        'provider': {'@id': base_url(request) + '/#organization'},
        'areaServed': {'@type': 'Country', 'name': 'ایران'},
    }


def page_context(request):
    """Everything base.html / partials/seo_head.html need for the current request."""
    match = getattr(request, 'resolver_match', None)
    url_name = match.url_name if match else None
    meta = PAGES.get(url_name)
    public = meta is not None
    crumbs = breadcrumbs(request, url_name) if public else []
    ld = []
    if url_name == 'home':
        ld += [organization(request), website(request)]
    elif url_name == 'contact':
        ld.append(organization(request))
    if crumbs:
        ld.append(breadcrumb_ld(crumbs))
    return {
        'url_name': url_name,
        'public': public,
        'robots': 'index, follow' if public else 'noindex, nofollow',
        'description': meta['description'] if meta else '',
        'canonical': base_url(request) + request.path,
        'breadcrumbs': crumbs,
        'jsonld': [ld_dumps(d) for d in ld],
        'site': site(),
        'base_url': base_url(request),
    }
