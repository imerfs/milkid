"""Shared builders for tests. Tests drive the app through URLs (the seam)."""
import itertools
import unittest
from datetime import date

from django.contrib.auth.models import User
from django.test import Client

from main.models import Payment, ServiceRequest, Municipality, CityVillage, UserProfile, Service, PropertyAdvertisement

_seq = itertools.count(1)


def make_user(role='citizen', **profile_extra):
    n = next(_seq)
    user = User.objects.create_user(username=f'{role}{n}', password='pw-test-12345')
    UserProfile.objects.filter(user=user).update(role=role, is_verified=True, **profile_extra)
    return user


def client_for(user=None):
    client = Client()
    if user is not None:
        client.force_login(user)
    return client


def make_payment(owner=None):
    owner = owner or make_user('citizen')
    n = next(_seq)
    return Payment.objects.create(
        user=owner, payment_type='property_tax', amount=1000,
        description='test', status='pending',
        receipt_number=f'R{n}', due_date=date(2030, 1, 1),
    )


def make_request(owner=None, **kwargs):
    owner = owner or make_user('citizen')
    fields = {'request_type': 'other', 'title': 't', 'description': 'd', **kwargs}
    return ServiceRequest.objects.create(user=owner, **fields)


def make_municipality(manager, village='روستای نمونه'):
    n = next(_seq)
    return Municipality.objects.create(
        name=f'دهیاری {n}', municipality_type='active', province='خراسان جنوبی', county='بیرجند',
        city_village=village, official_phone='09120000000', official_email='a@b.ir',
        postal_code='1234567890', address='addr', establishment_date=date(2020, 1, 1),
        population=100, area_hectares=1, manager_name='m', manager_national_id='1234567890',
        manager_phone='09120000000', manager_email='m@b.ir', admin_user=manager,
    )


def make_service(name='خدمت نمونه', slug='sample-service', **kwargs):
    return Service.objects.create(
        name=name, slug=slug, description='توضیح خدمت نمونه برای آزمایش',
        category='building', estimated_duration='3 days', required_documents='-', **kwargs)


def make_ad(status='approved', owner=None):
    owner = owner or make_user('citizen')
    return PropertyAdvertisement.objects.create(
        user=owner, ad_type='sale', property_type='land', total_area=100, address='addr',
        contact_name='n', contact_phone='09120000000', status=status)


def isolate_private_media(testcase):
    """Point PRIVATE_MEDIA_ROOT at a temporary folder for one test (backups and uploads must not land in the real one)."""
    import tempfile
    from django.test import override_settings
    folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    override = override_settings(PRIVATE_MEDIA_ROOT=folder.name)
    override.enable()
    testcase.addCleanup(override.disable)
    testcase.addCleanup(folder.cleanup)
    return folder.name


def _have_gis_data():
    from main.gis import loader
    return loader.VILLAGES['dastgerd']['file'].exists()


# the village maps are private (settings.GIS_DATA_DIR): a checkout without them still runs every test that does not need a real map
requires_gis_data = unittest.skipUnless(_have_gis_data(), 'the private village map data is not installed (docs/gis.md, "Private data")')
