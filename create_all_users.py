#!/usr/bin/env python
"""
Create users for all roles in MelkID system
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.contrib.auth.models import User
from main.models import UserProfile

def create_all_users():
    """Create users for all roles"""
    
    users_data = [
        # Admin
        {
            'username': 'admin',
            'password': 'admin123',
            'email': 'admin@melkid.ir',
            'first_name': 'مدیر',
            'last_name': 'سیستم',
            'national_id': '0000000000',
            'mobile': '09000000000',
            'role': 'admin',
            'is_superuser': True,
            'is_staff': True
        },
        
        # Citizen (شهروند)
        {
            'username': 'citizen1',
            'password': 'citizen123',
            'email': 'citizen@test.com',
            'first_name': 'احمد',
            'last_name': 'محمدی',
            'national_id': '1234567890',
            'mobile': '09123456789',
            'role': 'citizen'
        },
        
        # Dehyari (دهیار)
        {
            'username': 'dehyari1',
            'password': 'dehyari123',
            'email': 'dehyari@test.com',
            'first_name': 'علی',
            'last_name': 'کریمی',
            'national_id': '2345678901',
            'mobile': '09123456788',
            'role': 'dehyari'
        },
        
        # Engineer (کارشناس فنی)
        {
            'username': 'engineer1',
            'password': 'engineer123',
            'email': 'engineer@test.com',
            'first_name': 'مهندس حسن',
            'last_name': 'احمدی',
            'national_id': '3456789012',
            'mobile': '09123456787',
            'role': 'engineer'
        },
        
        # Council (عضو شورا)
        {
            'username': 'council1',
            'password': 'council123',
            'email': 'council@test.com',
            'first_name': 'رضا',
            'last_name': 'رضایی',
            'national_id': '4567890123',
            'mobile': '09123456786',
            'role': 'council'
        },
        
        # Accountant (مسئول مالی)
        {
            'username': 'accountant1',
            'password': 'accountant123',
            'email': 'accountant@test.com',
            'first_name': 'فاطمه',
            'last_name': 'حسینی',
            'national_id': '5678901234',
            'mobile': '09123456785',
            'role': 'accountant'
        },
        
        # Inspector (ناظر فنی)
        {
            'username': 'inspector1',
            'password': 'inspector123',
            'email': 'inspector@test.com',
            'first_name': 'مجید',
            'last_name': 'نظری',
            'national_id': '6789012345',
            'mobile': '09123456784',
            'role': 'inspector'
        },
    ]
    
    print("=" * 60)
    print("🚀 ایجاد کاربران برای تمام نقش‌ها")
    print("=" * 60)
    print()
    
    for user_data in users_data:
        try:
            # Check if user exists
            user = User.objects.filter(username=user_data['username']).first()
            
            if user:
                print(f"⚠️  کاربر {user_data['username']} از قبل وجود دارد - به‌روزرسانی...")
                action = "به‌روزرسانی"
            else:
                user = User()
                action = "ایجاد"
            
            # Set user fields
            user.username = user_data['username']
            user.email = user_data['email']
            user.first_name = user_data['first_name']
            user.last_name = user_data['last_name']
            user.is_active = True
            user.is_superuser = user_data.get('is_superuser', False)
            user.is_staff = user_data.get('is_staff', False)
            user.set_password(user_data['password'])
            user.save()
            
            # Get or create profile
            profile, created = UserProfile.objects.get_or_create(user=user)
            
            # Check if national_id is used by another user
            existing_profile = UserProfile.objects.filter(
                national_id=user_data['national_id']
            ).exclude(user=user).first()
            
            if existing_profile:
                # Update existing profile to avoid conflict
                existing_profile.national_id = f"{user_data['national_id']}_old"
                existing_profile.save()
            
            # Check if mobile is used by another user
            existing_mobile = UserProfile.objects.filter(
                mobile_number=user_data['mobile']
            ).exclude(user=user).first()
            
            if existing_mobile:
                # Update existing profile to avoid conflict
                existing_mobile.mobile_number = f"{user_data['mobile']}_old"
                existing_mobile.save()
            
            profile.national_id = user_data['national_id']
            profile.mobile_number = user_data['mobile']
            profile.father_name = user_data.get('father_name', '')
            profile.role = user_data['role']
            profile.is_verified = True
            profile.approval_status = 'approved'
            profile.is_active = True
            
            # Set location info (optional)
            profile.province = 'تهران'
            profile.county = 'شمیرانات'
            profile.district = 'مرکزی'
            profile.city_village = 'فشم'
            profile.dehestan_name = 'فشم'
            
            profile.save()
            
            role_persian = {
                'admin': 'مدیر سیستم',
                'citizen': 'شهروند',
                'dehyari': 'دهیار',
                'engineer': 'کارشناس فنی',
                'council': 'عضو شورا',
                'accountant': 'مسئول مالی',
                'inspector': 'ناظر فنی'
            }
            
            print(f"✅ {action} موفق: {user_data['username']}")
            print(f"   نام: {user.get_full_name()}")
            print(f"   نقش: {role_persian.get(user_data['role'], user_data['role'])}")
            print(f"   رمز عبور: {user_data['password']}")
            print()
            
        except Exception as e:
            print(f"❌ خطا در {user_data['username']}: {str(e)}")
            print()
    
    print("=" * 60)
    print("📊 خلاصه کاربران ایجاد شده")
    print("=" * 60)
    print()
    print("| نقش | نام کاربری | رمز عبور |")
    print("|-----|------------|----------|")
    print("| مدیر سیستم | admin | admin123 |")
    print("| شهروند | citizen1 | citizen123 |")
    print("| دهیار | dehyari1 | dehyari123 |")
    print("| کارشناس فنی | engineer1 | engineer123 |")
    print("| عضو شورا | council1 | council123 |")
    print("| مسئول مالی | accountant1 | accountant123 |")
    print("| ناظر فنی | inspector1 | inspector123 |")
    print()
    print("=" * 60)
    print("✅ تمام کاربران آماده‌اند!")
    print("=" * 60)
    print()
    print("🌐 برای ورود به سایت:")
    print("   http://127.0.0.1:8000")
    print()
    print("🔑 از هر کدام از نام کاربری‌ها و رمزهای بالا استفاده کنید")
    print()

if __name__ == '__main__':
    create_all_users()
