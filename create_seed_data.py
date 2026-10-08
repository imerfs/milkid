
#!/usr/bin/env python
import os
import django
from django.contrib.auth.models import User

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from main.models import UserProfile, Property, Service, ServiceRequest, Notification

def create_seed_data():
    """Create comprehensive seed data for MelkID system"""

    print("🌱 ایجاد داده‌های اولیه سیستم...")

    # Create Admin User
    print("👤 ایجاد کاربر مدیر...")
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@melkid.ir',
            'password': 'pbkdf2_sha256$600000$placeholder',  # Will be set properly
            'first_name': 'مدیر',
            'last_name': 'سیستم',
            'is_superuser': True,
            'is_staff': True,
            'is_active': True
        }
    )

    if created:
        admin_user.set_password('Admin@123456')
        admin_user.save()

        # Update admin profile
        profile = admin_user.profile
        profile.national_id = '0000000000'
        profile.mobile_number = '09000000000'
        profile.role = 'admin'
        profile.is_verified = True
        profile.save()
        print("✅ کاربر مدیر ایجاد شد")
    else:
        print("ℹ️ کاربر مدیر از قبل موجود است")

    # Create Dehyari User
    print("🏛️ ایجاد کاربر دهیاری...")
    dehyari_user, created = User.objects.get_or_create(
        username='dehyari.fasham',
        defaults={
            'email': 'dehyari@fasham.ir',
            'first_name': 'علی',
            'last_name': 'محمدی',
            'is_active': True
        }
    )

    if created:
        dehyari_user.set_password('Dehyari@123')
        dehyari_user.save()

        profile = dehyari_user.profile
        profile.national_id = '1234567890'
        profile.mobile_number = '09121234567'
        profile.role = 'dehyari'
        profile.is_verified = True
        profile.save()
        print("✅ کاربر دهیاری ایجاد شد")

    # Create Sample Property Owners
    print("🏠 ایجاد مالکان نمونه...")
    owners_data = [
        {
            'username': 'owner1', 'email': 'owner1@example.com',
            'first_name': 'احمد', 'last_name': 'رضایی',
            'national_id': '2345678901', 'mobile': '09131234567'
        },
        {
            'username': 'owner2', 'email': 'owner2@example.com', 
            'first_name': 'مریم', 'last_name': 'احمدی',
            'national_id': '3456789012', 'mobile': '09141234567'
        },
        {
            'username': 'owner3', 'email': 'owner3@example.com',
            'first_name': 'حسن', 'last_name': 'کریمی', 
            'national_id': '4567890123', 'mobile': '09151234567'
        }
    ]

    created_owners = []
    for owner_data in owners_data:
        owner, created = User.objects.get_or_create(
            username=owner_data['username'],
            defaults={
                'email': owner_data['email'],
                'first_name': owner_data['first_name'], 
                'last_name': owner_data['last_name'],
                'is_active': True
            }
        )

        if created:
            owner.set_password('Owner@123')
            owner.save()

            profile = owner.profile
            profile.national_id = owner_data['national_id']
            profile.mobile_number = owner_data['mobile']
            profile.role = 'owner'
            profile.is_verified = True
            profile.save()

        created_owners.append(owner)
        print(f"✅ مالک {owner.get_full_name()} ایجاد شد")

    # Create Sample Properties
    print("🏘️ ایجاد املاک نمونه...")
    properties_data = [
        {
            'title': 'ملک مسکونی ۲۰۰ متری فشم',
            'address': 'فشم، خیابان اصلی، پلاک ۱۵',
            'province': 'تهران',
            'county': 'شمیرانات',
            'village': 'فشم',
            'area': 200,
            'usage_type': 'residential',
            'has_debt': False,
            'description': 'ملک مسکونی در بهترین نقطه فشم با دسترسی آسان'
        },
        {
            'title': 'زمین کشاورزی ۱۵۰۰ متری',
            'address': 'فشم، حومه شرقی، قطعه A-15',
            'province': 'تهران', 
            'county': 'شمیرانات',
            'village': 'فشم',
            'area': 1500,
            'usage_type': 'agricultural',
            'has_debt': True,
            'description': 'زمین کشاورزی حاصلخیز با آب کشاورزی'
        },
        {
            'title': 'ملک تجاری ۱۰۰ متری',
            'address': 'لواسان، بازار محلی، واحد ۳',
            'province': 'تهران',
            'county': 'شمیرانات', 
            'village': 'لواسان',
            'area': 100,
            'usage_type': 'commercial',
            'has_debt': False,
            'description': 'مغازه در مرکز تجاری لواسان'
        }
    ]

    for i, prop_data in enumerate(properties_data):
        owner = created_owners[i % len(created_owners)]

        property_obj, created = Property.objects.get_or_create(
            title=prop_data['title'],
            defaults={
                'owner': owner,
                'address': prop_data['address'],
                'province': prop_data['province'],
                'county': prop_data['county'],
                'village': prop_data['village'],
                'area': prop_data['area'],
                'usage_type': prop_data['usage_type'],
                'has_debt': prop_data['has_debt'],
                'description': prop_data['description']
            }
        )

        if created:
            print(f"✅ ملک '{prop_data['title']}' ایجاد شد")

    # Create Additional Properties for Search Testing
    print("🔍 ایجاد املاک اضافی برای تست جستجو...")
    additional_properties = []
    villages = ['فشم', 'لواسان', 'رودهن', 'دستگرد', 'حاجی آباد']
    usage_types = ['residential', 'agricultural', 'commercial']

    for i in range(7):  # Create 7 more properties to total 10
        village = villages[i % len(villages)]
        usage = usage_types[i % len(usage_types)]
        owner = created_owners[i % len(created_owners)]

        property_obj, created = Property.objects.get_or_create(
            title=f'ملک {usage} {village} شماره {i+4}',
            defaults={
                'owner': owner,
                'address': f'{village}، منطقه {i+1}، پلاک {100+i}',
                'province': 'تهران' if village in ['فشم', 'لواسان', 'رودهن'] else 'خراسان جنوبی',
                'county': 'شمیرانات' if village in ['فشم', 'لواسان', 'رودهن'] else 'بیرجند',
                'village': village,
                'area': 150 + (i * 50),
                'usage_type': usage,
                'has_debt': i % 3 == 0,  # Every third property has debt
                'description': f'ملک {usage} در منطقه {village} با مساحت {150 + (i * 50)} متر مربع'
            }
        )

        if created:
            print(f"✅ ملک اضافی '{property_obj.title}' ایجاد شد")

    print("\n🎉 داده‌های اولیه با موفقیت ایجاد شد!")
    print("\n📊 خلاصه:")
    print(f"👥 کاربران: {User.objects.count()}")
    print(f"🏠 املاک: {Property.objects.count()}")
    print(f"🔧 خدمات: {Service.objects.count()}")

    print("\n🔐 اطلاعات ورود:")
    print("مدیر سیستم: admin / Admin@123456")
    print("دهیاری: dehyari.fasham / Dehyari@123") 
    print("مالک نمونه: owner1 / Owner@123")

if __name__ == '__main__':
    create_seed_data()
