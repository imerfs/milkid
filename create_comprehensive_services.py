#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from main.models import Service, ServiceStep, FAQ, LocalBusiness, Announcement
from django.contrib.auth.models import User


def create_comprehensive_services():
    """Create all required services and content"""

    print("🏗️ ایجاد خدمات جامع شهرداری...")

    # Building Permit Service (Enhanced)
    building_permit, created = Service.objects.get_or_create(
        slug='building-permit',
        defaults={
            'name':
            'صدور پروانه ساختمان',
            'description':
            'درخواست صدور پروانه ساختمان برای پروژه‌های جدید',
            'category':
            'building',
            'icon':
            '🏗️',
            'required_role':
            'owner',
            'estimated_duration':
            '15-30 روز کاری',
            'required_documents':
            '''• کپی سند مالکیت
• کپی کارت ملی مالک
• نقشه معماری
• گزارش خاک‌شناسی
• کپی پایان کار (در صورت وجود بنای قبلی)'''
        })

    # Property Deed Issuance
    property_deed, created = Service.objects.get_or_create(
        slug='property-deed-issuance',
        defaults={
            'name':
            'صدور سند ملک',
            'description':
            'صدور سند مالکیت برای املاک فاقد سند',
            'category':
            'property',
            'icon':
            '📜',
            'required_role':
            'owner',
            'estimated_duration':
            '30-45 روز کاری',
            'required_documents':
            '''• استشهادیه محلی
• کپی شناسنامه و کارت ملی
• عکس از ملک
• گواهی عدم دعوا'''
        })

    if created:
        ServiceStep.objects.create(service=property_deed,
                                   step_number=1,
                                   title='اطلاعات مالک',
                                   description='اطلاعات کامل مالک ملک',
                                   field_name='owner_info',
                                   field_type='textarea',
                                   field_label='اطلاعات کامل مالک',
                                   is_required=True)

        ServiceStep.objects.create(service=property_deed,
                                   step_number=2,
                                   title='مشخصات ملک',
                                   description='اطلاعات فنی و جغرافیایی ملک',
                                   field_name='property_specs',
                                   field_type='textarea',
                                   field_label='مشخصات کامل ملک',
                                   is_required=True)

    # Land Use Change
    land_use_change, created = Service.objects.get_or_create(
        slug='land-use-change',
        defaults={
            'name':
            'تغییر کاربری زمین',
            'description':
            'درخواست تغییر کاربری زمین (مسکونی، تجاری، کشاورزی)',
            'category':
            'property',
            'icon':
            '🗺️',
            'required_role':
            'owner',
            'estimated_duration':
            '45-60 روز کاری',
            'required_documents':
            '''• سند مالکیت
• نقشه کاداستر
• توجیه تغییر کاربری
• بررسی زیست‌محیطی'''
        })

    # Municipal Services
    trash_collection, created = Service.objects.get_or_create(
        slug='trash-collection',
        defaults={
            'name': 'درخواست جمع‌آوری زباله',
            'description': 'درخواست خدمات جمع‌آوری زباله و نظافت',
            'category': 'municipal',
            'icon': '🗑️',
            'required_role': 'resident',
            'estimated_duration': '1-3 روز کاری',
            'required_documents': 'عکس از محل انباشت زباله'
        })

    # Equipment Permits
    equipment_permit, created = Service.objects.get_or_create(
        slug='heavy-equipment-permit',
        defaults={
            'name':
            'مجوز تجهیزات سنگین',
            'description':
            'درخواست مجوز استفاده از تجهیزات سنگین و حفاری',
            'category':
            'municipal',
            'icon':
            '🚜',
            'required_role':
            'applicant',
            'estimated_duration':
            '7-10 روز کاری',
            'required_documents':
            '''• گواهی بیمه تجهیزات
• مجوز راهنمایی رانندگی
• طرح کار
• تعهدنامه بازسازی'''
        })

    # Event Permits
    event_permit_service, created = Service.objects.get_or_create(
        slug='event-ceremony-permit',
        defaults={
            'name':
            'مجوز برگزاری مراسم',
            'description':
            'صدور مجوز برای برگزاری مراسم و رویدادهای عمومی',
            'category':
            'municipal',
            'icon':
            '🎉',
            'required_role':
            'resident',
            'estimated_duration':
            '5-7 روز کاری',
            'required_documents':
            '''• شناسه برگزارکننده
• جزئیات مراسم
• نقشه محل
• بیمه مسئولیت'''
        })

    print("✅ خدمات اصلی ایجاد شد!")

    # Create FAQs
    print("📋 ایجاد سوالات متداول...")

    faqs = [{
        'category':
        'construction',
        'question':
        'چگونه می‌توانم پروانه ساختمان دریافت کنم؟',
        'answer':
        '''برای دریافت پروانه ساختمان مراحل زیر را طی کنید:
1. تهیه نقشه معماری از مهندس مجاز
2. بارگذاری مدارک در سامانه
3. پرداخت هزینه کارشناسی
4. بازدید کارشناس
5. صدور پروانه در صورت تایید'''
    }, {
        'category':
        'property',
        'question':
        'برای تغییر کاربری زمین چه مراحلی لازم است؟',
        'answer':
        '''مراحل تغییر کاربری:
1. ارائه درخواست همراه با مدارک
2. بررسی کارشناسی
3. تایید شورای روستا
4. پرداخت عوارض
5. صدور مجوز نهایی'''
    }, {
        'category':
        'legal',
        'question':
        'سند ملک من گم شده، چگونه جایگزین کنم؟',
        'answer':
        '''برای جایگزینی سند گمشده:
1. مراجعه به اداره ثبت اسناد
2. ارائه استشهادیه محلی
3. آگهی در روزنامه
4. تکمیل فرآیند قانونی
5. صدور سند جایگزین'''
    }, {
        'category':
        'payments',
        'question':
        'آیا امکان پرداخت اقساطی عوارض وجود دارد؟',
        'answer':
        '''بله، امکان پرداخت اقساطی برای:
• مالیات املاک
• عوارض نوسازی
• جرایم ساختمانی
• هزینه خدمات
حداکثر در 12 قسط موجود است.'''
    }, {
        'category':
        'general',
        'question':
        'ساعات کاری دهیاری چگونه است؟',
        'answer':
        '''ساعات کاری:
شنبه تا چهارشنبه: 8:00 تا 16:00
پنج‌شنبه: 8:00 تا 13:00
جمعه: تعطیل
تماس اضطراری: 09123456789'''
    }]

    for faq_data in faqs:
        FAQ.objects.get_or_create(question=faq_data['question'],
                                  defaults=faq_data)

    print("✅ سوالات متداول ایجاد شد!")

    # Create Local Businesses
    print("🏪 ایجاد کسب‌وکارهای محلی...")

    businesses = [{
        'name': 'فروشگاه مصالح سپهر',
        'business_type': 'construction',
        'description': 'فروش انواع مصالح ساختمانی، سیمان، آهن، آجر',
        'owner_name': 'احمد محمدی',
        'phone': '09121234567',
        'address': 'خیابان اصلی، جنب مسجد جامع',
        'is_verified': True,
        'rating': 4.5
    }, {
        'name': 'پیمانکاری کریمی',
        'business_type': 'contractor',
        'description': 'انجام کلیه کارهای ساختمانی، تعمیرات و بازسازی',
        'owner_name': 'علی کریمی',
        'phone': '09131234567',
        'address': 'میدان مرکزی، پلاک 45',
        'is_verified': True,
        'rating': 4.8
    }, {
        'name': 'اجاره ماشین‌آلات پارسا',
        'business_type': 'equipment',
        'description': 'اجاره بیل مکانیکی، لودر، کمپرسی و سایر ماشین‌آلات',
        'owner_name': 'مهدی پارسا',
        'phone': '09141234567',
        'address': 'جاده ورودی روستا',
        'is_verified': True,
        'rating': 4.2
    }]

    for business_data in businesses:
        LocalBusiness.objects.get_or_create(name=business_data['name'],
                                            defaults=business_data)

    print("✅ کسب‌وکارهای محلی ایجاد شد!")

    # Create Sample Announcement
    try:
        admin_user = User.objects.filter(profile__role='admin').first()
        if admin_user:
            Announcement.objects.get_or_create(
                title='خوش آمدگویی به سامانه جدید',
                defaults={
                    'content': '''کاربران گرامی،
سامانه جدید خدمات روستایی "بهرانگار سامانداد" راه‌اندازی شد.

امکانات جدید:
• درخواست آنلاین خدمات
• پیگیری وضعیت درخواست‌ها
• پرداخت آنلاین عوارض
• گزارش تخلفات
• ثبت پیشنهادات و شکایات

برای راهنمایی بیشتر با شماره 09123456789 تماس بگیرید.''',
                    'priority': 'high',
                    'target_roles': ['all'],
                    'created_by': admin_user,
                    'is_active': True
                })
            print("✅ اطلاعیه خوش‌آمدگویی ایجاد شد!")
    except:
        print("⚠️ امکان ایجاد اطلاعیه وجود ندارد (کاربر مدیر یافت نشد)")

    print("\n🎉 تمام خدمات و محتوای سامانه با موفقیت ایجاد شد!")
    print("📊 خلاصه:")
    print(f"• خدمات: {Service.objects.count()}")
    print(f"• سوالات متداول: {FAQ.objects.count()}")
    print(f"• کسب‌وکارها: {LocalBusiness.objects.count()}")
    print(f"• اطلاعیه‌ها: {Announcement.objects.count()}")


if __name__ == '__main__':
    create_comprehensive_services()
