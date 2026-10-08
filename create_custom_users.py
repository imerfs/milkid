#!/usr/bin/env python
"""
اسکریپت ساخت کاربران سفارشی برای تست سیستم MelkID
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.contrib.auth.models import User
from main.models import UserProfile, Province, County, District, Dehestan, CityVillage

def create_custom_user(
    username,
    password,
    first_name,
    last_name,
    role,
    email=None,
    mobile_number=None,
    national_id=None,
    province_name=None,
    county_name=None,
    district_name=None,
    dehestan_name=None,
    city_village_name=None,
    is_village=False
):
    """
    ساخت کاربر سفارشی با جزئیات کامل
    
    Args:
        username: نام کاربری (انگلیسی)
        password: رمز عبور
        first_name: نام
        last_name: نام خانوادگی
        role: نقش کاربر (citizen, owner, resident, dehyari, engineer, inspector, accountant, council, admin)
        email: ایمیل (اختیاری)
        mobile_number: شماره موبایل (اختیاری)
        national_id: کد ملی (اختیاری)
        province_name: نام استان (اختیاری)
        county_name: نام شهرستان (اختیاری)
        district_name: نام بخش (اختیاری)
        dehestan_name: نام دهستان (اختیاری)
        city_village_name: نام شهر/روستا (اختیاری)
        is_village: آیا روستا است؟ (پیش‌فرض: False)
    """
    
    # بررسی وجود کاربر
    if User.objects.filter(username=username).exists():
        print(f"❌ کاربر '{username}' قبلاً وجود دارد!")
        return None
    
    try:
        # ایجاد کاربر Django
        is_staff = role in ['admin', 'dehyari', 'engineer', 'accountant', 'council', 'inspector']
        is_superuser = role == 'admin'
        
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email or f"{username}@test.com",
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        
        # بررسی اگر پروفایل از قبل وجود داشت (ممکن است از طریق سیگنال ساخته شده باشد)
        if hasattr(user, 'profile'):
            profile = user.profile
            # به‌روزرسانی پروفایل موجود
            profile.role = role
            profile.national_id = national_id
            profile.mobile_number = mobile_number
            profile.province = province_name
            profile.county = county_name
            profile.district = district_name
            profile.dehestan_name = dehestan_name
            profile.city_village_name = city_village_name
            profile.is_village = is_village
            profile.is_verified = True
            profile.is_active = True
            profile.approval_status = 'approved'
            profile.save()
            created_new = False
        else:
            # ایجاد پروفایل جدید
            profile = UserProfile.objects.create(
                user=user,
                role=role,
                national_id=national_id,
                mobile_number=mobile_number,
                province=province_name,
                county=county_name,
                district=district_name,
                dehestan_name=dehestan_name,
                city_village_name=city_village_name,
                is_village=is_village,
                is_verified=True,
                is_active=True,
                approval_status='approved'
            )
            created_new = True
        
        location = []
        if province_name:
            location.append(f"استان {province_name}")
        if county_name:
            location.append(f"شهرستان {county_name}")
        if district_name:
            location.append(f"بخش {district_name}")
        if dehestan_name:
            location.append(f"دهستان {dehestan_name}")
        if city_village_name:
            location.append(f"{'روستا' if is_village else 'شهر'} {city_village_name}")
        
        location_str = " > ".join(location) if location else "تعریف نشده"
        
        print(f"✅ کاربر '{username}' با موفقیت ایجاد شد")
        print(f"   نقش: {profile.get_role_display()}")
        print(f"   محل: {location_str}")
        
        return user
        
    except Exception as e:
        print(f"❌ خطا در ایجاد کاربر '{username}': {str(e)}")
        return None


def show_available_locations():
    """نمایش استان‌ها و شهرستان‌های موجود در سیستم"""
    print("\n" + "="*80)
    print("📍 لیست استان‌ها و شهرستان‌های موجود در سیستم")
    print("="*80)
    
    provinces = Province.objects.all()
    
    if not provinces.exists():
        print("⚠️  هیچ اطلاعات جغرافیایی در سیستم وجود ندارد!")
        print("💡 ابتدا فایل import_geographic_data.py را اجرا کنید")
        return
    
    for province in provinces:
        print(f"\n🔹 استان: {province.name}")
        counties = County.objects.filter(province=province)
        for county in counties:
            print(f"   └─ شهرستان: {county.name}")
            districts = District.objects.filter(county=county)
            for district in districts:
                print(f"      └─ بخش: {district.name}")
    
    print("\n" + "="*80)


def create_sample_users():
    """ساخت چند کاربر نمونه در شهرهای مختلف"""
    print("\n🚀 ساخت کاربران نمونه در شهرهای مختلف...")
    print("="*80 + "\n")
    
    # کاربر نمونه 1: تهران
    create_custom_user(
        username="citizen_tehran",
        password="test123",
        first_name="محمد",
        last_name="تهرانی",
        role="citizen",
        mobile_number="09121234567",
        national_id="0012345678",
        province_name="تهران",
        county_name="تهران",
        district_name="مرکزی",
        city_village_name="تهران",
        is_village=False
    )
    
    # کاربر نمونه 2: مشهد
    create_custom_user(
        username="citizen_mashhad",
        password="test123",
        first_name="علی",
        last_name="مشهدی",
        role="citizen",
        mobile_number="09151234567",
        national_id="0012345679",
        province_name="خراسان رضوی",
        county_name="مشهد",
        district_name="مرکزی",
        city_village_name="مشهد",
        is_village=False
    )
    
    # کاربر نمونه 3: دهیار روستایی
    create_custom_user(
        username="dehyari_village",
        password="test123",
        first_name="حسین",
        last_name="روستایی",
        role="dehyari",
        mobile_number="09361234567",
        national_id="0012345680",
        province_name="مازندران",
        county_name="ساری",
        district_name="مرکزی",
        dehestan_name="سنگر",
        city_village_name="روستای نمونه",
        is_village=True
    )
    
    print("\n" + "="*80)
    print("✨ ساخت کاربران نمونه به پایان رسید!")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--locations':
        show_available_locations()
    elif len(sys.argv) > 1 and sys.argv[1] == '--samples':
        create_sample_users()
    else:
        print("\n" + "="*80)
        print("📝 راهنمای استفاده از اسکریپت ساخت کاربران سفارشی")
        print("="*80)
        print("\n🔹 نمایش استان‌ها و شهرستان‌های موجود:")
        print("   python create_custom_users.py --locations")
        print("\n🔹 ساخت کاربران نمونه:")
        print("   python create_custom_users.py --samples")
        print("\n🔹 ساخت کاربر سفارشی (در کد Python):")
        print("""
from create_custom_users import create_custom_user

create_custom_user(
    username="test_user",
    password="test123",
    first_name="نام",
    last_name="نام خانوادگی",
    role="citizen",  # citizen, owner, resident, dehyari, engineer, inspector, accountant, council, admin
    mobile_number="09121234567",
    national_id="0012345678",
    province_name="تهران",
    county_name="تهران",
    district_name="مرکزی",
    city_village_name="تهران",
    is_village=False
)
        """)
        print("\n💡 نقش‌های قابل استفاده:")
        print("   • citizen = شهروند")
        print("   • owner = مالک")
        print("   • resident = ساکن")
        print("   • dehyari = دهیار")
        print("   • engineer = کارشناس فنی")
        print("   • inspector = ناظر فنی")
        print("   • accountant = مسئول مالی")
        print("   • council = عضو شورا")
        print("   • admin = مدیر سیستم")
        print("\n" + "="*80)
