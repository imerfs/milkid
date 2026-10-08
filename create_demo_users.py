#!/usr/bin/env python
"""
اسکریپت ایجاد کاربرهای نمونه برای تست سیستم MelkID
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.contrib.auth.models import User
from main.models import UserProfile

def create_demo_users():
    """ایجاد کاربرهای نمونه با نقش‌های مختلف"""
    
    users_data = [
        {
            'username': 'admin',
            'password': 'admin123',
            'first_name': 'مدیر',
            'last_name': 'سیستم',
            'email': 'admin@melkid.ir',
            'role': 'admin',
            'national_id': '1234567890',
            'mobile_number': '09123456789',
            'city_village': 'تهران',
            'province': 'تهران',
            'county': 'تهران',
            'is_superuser': True,
            'is_staff': True,
        },
        {
            'username': 'citizen1',
            'password': 'citizen123',
            'first_name': 'علی',
            'last_name': 'احمدی',
            'email': 'citizen1@melkid.ir',
            'role': 'citizen',
            'national_id': '1234567891',
            'mobile_number': '09123456790',
            'city_village': 'کرج',
            'province': 'البرز',
            'county': 'کرج',
        },
        {
            'username': 'dehyari1',
            'password': 'dehyari123',
            'first_name': 'محمد',
            'last_name': 'رضایی',
            'email': 'dehyari1@melkid.ir',
            'role': 'dehyari',
            'national_id': '1234567892',
            'mobile_number': '09123456791',
            'city_village': 'روستای نمونه',
            'province': 'البرز',
            'county': 'کرج',
            'is_staff': True,
        },
        {
            'username': 'engineer1',
            'password': 'engineer123',
            'first_name': 'حسن',
            'last_name': 'مهندسی',
            'email': 'engineer1@melkid.ir',
            'role': 'engineer',
            'national_id': '1234567893',
            'mobile_number': '09123456792',
            'city_village': 'کرج',
            'province': 'البرز',
            'county': 'کرج',
            'is_staff': True,
        },
        {
            'username': 'council1',
            'password': 'council123',
            'first_name': 'فاطمه',
            'last_name': 'شورایی',
            'email': 'council1@melkid.ir',
            'role': 'council',
            'national_id': '1234567894',
            'mobile_number': '09123456793',
            'city_village': 'روستای نمونه',
            'province': 'البرز',
            'county': 'کرج',
            'is_staff': True,
        },
        {
            'username': 'accountant1',
            'password': 'accountant123',
            'first_name': 'رضا',
            'last_name': 'حسابدار',
            'email': 'accountant1@melkid.ir',
            'role': 'accountant',
            'national_id': '1234567895',
            'mobile_number': '09123456794',
            'city_village': 'کرج',
            'province': 'البرز',
            'county': 'کرج',
            'is_staff': True,
        },
        {
            'username': 'inspector1',
            'password': 'inspector123',
            'first_name': 'احمد',
            'last_name': 'بازرس',
            'email': 'inspector1@melkid.ir',
            'role': 'inspector',
            'national_id': '1234567896',
            'mobile_number': '09123456795',
            'city_village': 'کرج',
            'province': 'البرز',
            'county': 'کرج',
            'is_staff': True,
        },
    ]
    
    created_users = []
    
    for user_data in users_data:
        username = user_data['username']
        
        # بررسی وجود کاربر
        if User.objects.filter(username=username).exists():
            print(f"⚠️  کاربر {username} قبلاً وجود دارد، رد می‌شود...")
            continue
            
        try:
            # ایجاد کاربر Django
            user = User.objects.create_user(
                username=user_data['username'],
                password=user_data['password'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                email=user_data['email'],
                is_superuser=user_data.get('is_superuser', False),
                is_staff=user_data.get('is_staff', False),
            )
            
            # ایجاد پروفایل کاربری
            profile = UserProfile.objects.create(
                user=user,
                role=user_data['role'],
                national_id=user_data['national_id'],
                mobile_number=user_data['mobile_number'],
                city_village=user_data['city_village'],
                province=user_data['province'],
                county=user_data['county'],
                is_verified=True,
                is_active=True,
                approval_status='approved',
            )
            
            created_users.append({
                'username': username,
                'role': user_data['role'],
                'name': f"{user_data['first_name']} {user_data['last_name']}"
            })
            
            print(f"✅ کاربر {username} ({user_data['role']}) با موفقیت ایجاد شد")
            
        except Exception as e:
            print(f"❌ خطا در ایجاد کاربر {username}: {str(e)}")
    
    return created_users

def print_user_table(users):
    """چاپ جدول کاربران ایجاد شده"""
    print("\n" + "="*80)
    print("🎉 کاربران نمونه با موفقیت ایجاد شدند!")
    print("="*80)
    print(f"{'نقش':<15} {'نام کاربری':<15} {'رمز عبور':<15} {'نام کامل':<20}")
    print("-"*80)
    
    role_names = {
        'admin': 'مدیر سیستم',
        'citizen': 'شهروند', 
        'dehyari': 'دهیار',
        'engineer': 'کارشناس فنی',
        'council': 'عضو شورا',
        'accountant': 'مسئول مالی',
        'inspector': 'ناظر فنی',
    }
    
    for user in users:
        role_display = role_names.get(user['role'], user['role'])
        print(f"{role_display:<15} {user['username']:<15} {'***':<15} {user['name']:<20}")
    
    print("-"*80)
    print("🌐 برای ورود به سیستم از آدرس http://127.0.0.1:8000 استفاده کنید")
    print("📝 رمزهای عبور:")
    print("   - admin: admin123")
    print("   - citizen1: citizen123") 
    print("   - dehyari1: dehyari123")
    print("   - engineer1: engineer123")
    print("   - council1: council123")
    print("   - accountant1: accountant123")
    print("   - inspector1: inspector123")
    print("="*80)

if __name__ == '__main__':
    print("🚀 شروع ایجاد کاربران نمونه...")
    created_users = create_demo_users()
    
    if created_users:
        print_user_table(created_users)
    else:
        print("⚠️  هیچ کاربر جدیدی ایجاد نشد (احتمالاً همه قبلاً وجود داشتند)")
    
    print("\n✨ تمام!")