#!/usr/bin/env python
"""
اسکریپت سریع برای ساخت کاربر جدید
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.contrib.auth.models import User
from main.models import UserProfile

# ⚙️ تنظیمات کاربر جدید - اینجا رو ویرایش کن:

USERNAME = "test_user_new"          # نام کاربری (انگلیسی)
PASSWORD = "test123"                # رمز عبور
FIRST_NAME = "کاربر"                # نام
LAST_NAME = "تستی"                  # نام خانوادگی
ROLE = "citizen"                    # نقش: citizen, owner, resident, dehyari, engineer, inspector, accountant, council, admin
MOBILE = "09123456700"              # شماره موبایل
NATIONAL_ID = "0123456789"          # کد ملی
EMAIL = "test@test.com"             # ایمیل

# اطلاعات جغرافیایی (اختیاری)
PROVINCE = "اصفهان"                 # استان
COUNTY = "اصفهان"                   # شهرستان
DISTRICT = "مرکزی"                  # بخش
DEHESTAN = None                     # دهستان (برای روستا)
CITY_VILLAGE = "اصفهان"             # شهر/روستا
IS_VILLAGE = False                  # True اگر روستا باشه

# ═══════════════════════════════════════════════════════════════

def create_user():
    """ساخت کاربر با تنظیمات بالا"""
    
    # بررسی وجود کاربر
    if User.objects.filter(username=USERNAME).exists():
        print(f"❌ کاربر '{USERNAME}' قبلاً وجود دارد!")
        user = User.objects.get(username=USERNAME)
        print(f"💡 می‌خواهی اطلاعات '{USERNAME}' رو آپدیت کنی؟")
        return
    
    try:
        # تعیین دسترسی‌ها
        is_staff = ROLE in ['admin', 'dehyari', 'engineer', 'accountant', 'council', 'inspector']
        is_superuser = ROLE == 'admin'
        
        # ساخت کاربر
        user = User.objects.create_user(
            username=USERNAME,
            password=PASSWORD,
            first_name=FIRST_NAME,
            last_name=LAST_NAME,
            email=EMAIL,
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        
        # مدیریت پروفایل
        if hasattr(user, 'profile'):
            profile = user.profile
        else:
            profile = UserProfile.objects.create(user=user)
        
        # تنظیم اطلاعات پروفایل
        profile.role = ROLE
        profile.national_id = NATIONAL_ID
        profile.mobile_number = MOBILE
        profile.province = PROVINCE
        profile.county = COUNTY
        profile.district = DISTRICT
        profile.dehestan_name = DEHESTAN
        profile.city_village_name = CITY_VILLAGE
        profile.is_village = IS_VILLAGE
        profile.is_verified = True
        profile.is_active = True
        profile.approval_status = 'approved'
        profile.save()
        
        # نمایش نتیجه
        print("\n" + "="*80)
        print("✅ کاربر با موفقیت ایجاد شد!")
        print("="*80)
        print(f"👤 نام کاربری: {USERNAME}")
        print(f"🔑 رمز عبور: {PASSWORD}")
        print(f"📛 نام کامل: {FIRST_NAME} {LAST_NAME}")
        print(f"👔 نقش: {profile.get_role_display()}")
        print(f"📱 موبایل: {MOBILE}")
        print(f"🆔 کد ملی: {NATIONAL_ID}")
        
        location_parts = []
        if PROVINCE:
            location_parts.append(f"استان {PROVINCE}")
        if COUNTY:
            location_parts.append(f"شهرستان {COUNTY}")
        if DISTRICT:
            location_parts.append(f"بخش {DISTRICT}")
        if DEHESTAN:
            location_parts.append(f"دهستان {DEHESTAN}")
        if CITY_VILLAGE:
            location_parts.append(f"{'روستا' if IS_VILLAGE else 'شهر'} {CITY_VILLAGE}")
        
        if location_parts:
            print(f"📍 محل: {' > '.join(location_parts)}")
        
        print("="*80)
        print("🌐 برای ورود به http://127.0.0.1:8000 بروید")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"❌ خطا: {str(e)}")

if __name__ == '__main__':
    print("\n🚀 ساخت کاربر جدید...")
    print("="*80)
    print("💡 برای تغییر اطلاعات، فایل quick_create_user.py را ویرایش کنید")
    print("="*80 + "\n")
    create_user()
