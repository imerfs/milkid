
#!/usr/bin/env python
import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from main.models import Property
from django.contrib.auth.models import User

def create_sample_properties():
    """Create sample properties for testing"""

    # Get admin user for created_by field
    try:
        admin_user = User.objects.filter(is_superuser=True).first()
    except:
        admin_user = None

    sample_properties = [
        {
            'parcel_number': '12345',
            'deed_number': 'S-1001',
            'address': 'تهران، خیابان آزادی، کوچه شهید محمدی، پلاک 15',
            'area': Decimal('250.50'),
            'usage_type': 'residential',
            'location_area': 'center',
            'owner_name': 'احمد محمدی',
            'owner_national_id': '1234567890',
            'owner_phone': '09121234567',
            'construction_year': 1395,
            'floors': 2,
            'units': 1,
            'parking_spaces': 1,
            'assessed_value': Decimal('5500000000'),
            'market_price': Decimal('6000000000'),
            'annual_tax': Decimal('2750000'),
            'status': 'active',
            'created_by': admin_user,
        },
        {
            'parcel_number': '12346',
            'deed_number': 'S-1002',
            'address': 'تهران، خیابان انقلاب، کوچه دانشگاه، پلاک 8',
            'area': Decimal('180.00'),
            'usage_type': 'commercial',
            'location_area': 'center',
            'owner_name': 'فاطمه احمدی',
            'owner_national_id': '0987654321',
            'owner_phone': '09139876543',
            'construction_year': 1385,
            'floors': 1,
            'units': 2,
            'parking_spaces': 0,
            'assessed_value': Decimal('8000000000'),
            'market_price': Decimal('8500000000'),
            'annual_tax': Decimal('4000000'),
            'status': 'active',
            'is_for_sale': True,
            'created_by': admin_user,
        },
        {
            'parcel_number': '12347',
            'deed_number': 'S-1003',
            'address': 'کرج، شهرک مهستان، خیابان گلستان، پلاک 25',
            'area': Decimal('5000.00'),
            'usage_type': 'agricultural',
            'location_area': 'west',
            'owner_name': 'علی کریمی',
            'owner_national_id': '1122334455',
            'owner_phone': '09151122334',
            'construction_year': None,
            'floors': 0,
            'units': 0,
            'parking_spaces': 0,
            'assessed_value': Decimal('2000000000'),
            'market_price': Decimal('2500000000'),
            'annual_tax': Decimal('1000000'),
            'status': 'active',
            'created_by': admin_user,
        },
        {
            'parcel_number': '12348',
            'deed_number': 'S-1004',
            'address': 'تهران، خیابان ولیعصر، برج مسکونی آریا، طبقه 15',
            'area': Decimal('120.00'),
            'usage_type': 'residential',
            'location_area': 'north',
            'owner_name': 'مریم صادقی',
            'owner_national_id': '5566778899',
            'owner_phone': '09165566778',
            'construction_year': 1400,
            'floors': 20,
            'units': 80,
            'parking_spaces': 1,
            'assessed_value': Decimal('4000000000'),
            'market_price': Decimal('4500000000'),
            'annual_tax': Decimal('2000000'),
            'status': 'active',
            'is_for_rent': True,
            'created_by': admin_user,
        },
        {
            'parcel_number': '12349',
            'deed_number': 'S-1005',
            'address': 'شهریار، منطقه صنعتی، خیابان صنعت، پلاک 100',
            'area': Decimal('2000.00'),
            'usage_type': 'industrial',
            'location_area': 'south',
            'owner_name': 'شرکت تولیدی سپهر',
            'owner_national_id': '1111222233',
            'owner_phone': '09121111222',
            'construction_year': 1390,
            'floors': 1,
            'units': 1,
            'parking_spaces': 10,
            'assessed_value': Decimal('15000000000'),
            'market_price': Decimal('18000000000'),
            'annual_tax': Decimal('7500000'),
            'status': 'active',
            'created_by': admin_user,
        },
    ]

    created_count = 0
    for prop_data in sample_properties:
        prop, created = Property.objects.get_or_create(
            parcel_number=prop_data['parcel_number'],
            defaults=prop_data
        )
        if created:
            created_count += 1
            print(f"✅ ملک {prop.parcel_number} - {prop.owner_name} ایجاد شد")
        else:
            print(f"⚠️ ملک {prop.parcel_number} از قبل موجود است")

    print(f"\n📊 خلاصه: {created_count} ملک جدید ایجاد شد از {len(sample_properties)} ملک")
    print(f"📋 کل املاک در سیستم: {Property.objects.count()}")

if __name__ == '__main__':
    create_sample_properties()
