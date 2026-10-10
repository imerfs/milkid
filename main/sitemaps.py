from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from main.models import PropertyAdvertisement, Service
from main.seo import PAGES


class StaticPages(Sitemap):
    def items(self):
        return [name for name, meta in PAGES.items() if meta.get('sitemap')]

    def location(self, name):
        return reverse(f'main:{name}')

    def changefreq(self, name):
        return PAGES[name]['changefreq']

    def priority(self, name):
        return PAGES[name]['priority']


class Services(Sitemap):
    changefreq = 'monthly'
    priority = 0.7

    def items(self):
        return Service.objects.filter(is_active=True).order_by('slug')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('main:service_detail', args=[obj.slug])


class PropertyAds(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return PropertyAdvertisement.objects.filter(status='approved').order_by('-updated_at')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('main:property_detail', args=[obj.id])


SITEMAPS = {'pages': StaticPages, 'services': Services, 'properties': PropertyAds}
