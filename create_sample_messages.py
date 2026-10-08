#!/usr/bin/env python
"""
اسکریپت ایجاد پیام‌ها و اطلاعیه‌های نمونه برای تست سیستم پیام‌رسانی
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.contrib.auth.models import User
from main.models import (
    UserProfile, Conversation, Message, MessageRecipient, 
    Notification, Announcement, ServiceRequest
)
from django.utils import timezone

def create_sample_announcements():
    """ایجاد اطلاعیه‌های نمونه"""
    print("🔔 ایجاد اطلاعیه‌های نمونه...")
    
    try:
        # پیدا کردن دهیار
        dehyari = User.objects.filter(profile__role='dehyari').first()
        if not dehyari:
            print("❌ دهیار یافت نشد")
            return
        
        announcements_data = [
            {
                'title': 'اطلاعیه قطعی آب شرب',
                'content': '''به اطلاع ساکنین محترم می‌رساند که به دلیل تعمیرات اساسی خط لوله اصلی آب شرب، آب روستا در تاریخ ۱۴۰۳/۰۸/۲۵ از ساعت ۸ صبح الی ۱۶ قطع خواهد بود.

لطفاً تمهیدات لازم را در نظر بگیرید و از ذخیره‌سازی آب برای مصارف ضروری اقدام فرمایید.

با تشکر
دهیاری روستا''',
                'priority': 'high',
                'target_roles': ['citizen', 'owner', 'resident'],
            },
            {
                'title': 'دعوت به جلسه شورای روستا',
                'content': '''جلسه فوق‌العاده شورای اسلامی روستا جهت بررسی موارد زیر در تاریخ ۱۴۰۳/۰۸/۳۰ ساعت ۱۹ در محل دهیاری برگزار خواهد شد:

۱. بررسی بودجه سال آینده
۲. تصویب طرح‌های عمرانی
۳. بررسی شکایات مردمی
۴. سایر موارد

حضور تمامی اعضای محترم شورا الزامی است.''',
                'priority': 'medium',
                'target_roles': ['council'],
            },
            {
                'title': 'آغاز ثبت‌نام کلاس‌های آموزشی',
                'content': '''با سلام و احترام

ثبت‌نام کلاس‌های آموزشی زیر از تاریخ ۱۴۰۳/۰۹/۰۱ آغاز می‌شود:

🔸 کلاس کامپیوتر (مبتدی و پیشرفته)
🔸 کلاس زبان انگلیسی
🔸 کلاس خیاطی و طراحی
🔸 کلاس آشپزی سنتی

برای ثبت‌نام به دهیاری مراجعه کنید یا با شماره ۰۲۱-۱۲۳۴۵۶۷۸ تماس بگیرید.

ظرفیت محدود است.''',
                'priority': 'low',
                'target_roles': [],  # همه کاربران
            },
            {
                'title': 'هشدار امنیتی - احتیاط در برابر کلاهبرداری',
                'content': '''⚠️ هشدار امنیتی مهم ⚠️

اخیراً موارد کلاهبرداری تلفنی در منطقه گزارش شده است. لطفاً نکات زیر را رعایت کنید:

❌ هیچ‌گاه اطلاعات بانکی خود را تلفنی اعلام نکنید
❌ به پیامک‌های مشکوک پاسخ ندهید
❌ روی لینک‌های ناشناس کلیک نکنید
✅ در صورت شک، با دهیاری تماس بگیرید

شماره تماس اضطراری: ۱۱۰''',
                'priority': 'urgent',
                'target_roles': [],  # همه کاربران
            },
        ]
        
        created_count = 0
        for ann_data in announcements_data:
            announcement = Announcement.objects.create(
                title=ann_data['title'],
                content=ann_data['content'],
                priority=ann_data['priority'],
                target_roles=ann_data['target_roles'],
                created_by=dehyari,
                is_active=True
            )
            created_count += 1
            print(f"✅ اطلاعیه '{announcement.title}' ایجاد شد")
        
        print(f"🎉 {created_count} اطلاعیه نمونه ایجاد شد")
        
    except Exception as e:
        print(f"❌ خطا در ایجاد اطلاعیه‌ها: {str(e)}")

def create_sample_conversations():
    """ایجاد مکالمات نمونه"""
    print("\n💬 ایجاد مکالمات نمونه...")
    
    try:
        # پیدا کردن کاربران
        citizen = User.objects.filter(profile__role='citizen').first()
        dehyari = User.objects.filter(profile__role='dehyari').first()
        engineer = User.objects.filter(profile__role='engineer').first()
        
        if not all([citizen, dehyari, engineer]):
            print("❌ کاربران مورد نیاز یافت نشدند")
            return
        
        conversations_data = [
            {
                'subject': 'سوال درباره پروانه ساختمان',
                'participants': [citizen, dehyari],
                'messages': [
                    {
                        'sender': citizen,
                        'body': '''سلام وقت بخیر
من می‌خواهم برای ساخت یک خانه ویلایی در زمین خودم پروانه بگیرم. لطفاً راهنمایی کنید که چه مدارکی لازم است؟
با تشکر'''
                    },
                    {
                        'sender': dehyari,
                        'body': '''سلام علیکم
برای دریافت پروانه ساختمان مدارک زیر لازم است:
۱. کپی سند مالکیت
۲. نقشه معماری تایید شده
۳. نقشه سازه
۴. کپی کارت ملی
۵. عکس ۴×۳

می‌توانید از بخش خدمات سایت درخواست آنلاین ثبت کنید.'''
                    },
                    {
                        'sender': citizen,
                        'body': 'ممنون از راهنمایی‌تان. آیا امکان بازدید از محل وجود دارد؟'
                    },
                    {
                        'sender': dehyari,
                        'body': 'بله حتماً. کارشناس فنی ما برای بازدید اولیه به محل خواهد آمد. زمان مناسب برای شما چه موقع است؟'
                    }
                ]
            },
            {
                'subject': 'گزارش مشکل آب و فاضلاب',
                'participants': [citizen, engineer],
                'messages': [
                    {
                        'sender': citizen,
                        'body': '''سلام
در خیابان شهید بهشتی، نرسیده به چهارراه اول، لوله فاضلاب ترکیده و بوی بدی پیچیده.
لطفاً پیگیری کنید.
آدرس دقیق: خیابان شهید بهشتی، پلاک ۱۲۳'''
                    },
                    {
                        'sender': engineer,
                        'body': '''سلام
ممنون از گزارش شما. گروه تعمیرات فردا صبح به محل اعزام می‌شوند.
شماره پیگیری: ۱۴۰۳۰۸۲۵-۰۰۱
در صورت عدم رسیدگی تا ظهر فردا، مجدداً تماس بگیرید.'''
                    },
                    {
                        'sender': citizen,
                        'body': 'ممنون. منتظر هستم.'
                    }
                ]
            },
            {
                'subject': 'درخواست تایید سکونت',
                'participants': [citizen, dehyari],
                'messages': [
                    {
                        'sender': citizen,
                        'body': '''سلام
برای ثبت‌نام فرزندم در مدرسه نیاز به تایید سکونت دارم.
کد ملی: ۱۲۳۴۵۶۷۸۹۰
آدرس: خیابان امام خمینی، کوچه گلستان، پلاک ۴۵
لطفاً راهنمایی کنید.'''
                    },
                    {
                        'sender': dehyari,
                        'body': '''سلام
برای صدور تایید سکونت لطفاً موارد زیر را آماده کنید:
۱. کپی کارت ملی
۲. کپی شناسنامه فرزند
۳. قبض آب یا برق
۴. تصویر قولنامه یا سند

می‌توانید از طریق سایت درخواست دهید یا حضوری به دهیاری مراجعه کنید.'''
                    }
                ]
            }
        ]
        
        created_count = 0
        for conv_data in conversations_data:
            # ایجاد مکالمه
            conversation = Conversation.objects.create(
                subject=conv_data['subject']
            )
            
            # اضافه کردن شرکت‌کنندگان
            for participant in conv_data['participants']:
                conversation.participants.add(participant)
            
            # ایجاد پیام‌ها
            for i, msg_data in enumerate(conv_data['messages']):
                message = Message.objects.create(
                    conversation=conversation,
                    sender=msg_data['sender'],
                    body=msg_data['body'],
                    created_at=timezone.now() - timedelta(hours=len(conv_data['messages'])-i)
                )
                
                # ایجاد MessageRecipient برای سایر شرکت‌کنندگان
                for participant in conv_data['participants']:
                    if participant != msg_data['sender']:
                        MessageRecipient.objects.create(
                            message=message,
                            recipient=participant,
                            is_read=(i < len(conv_data['messages']) - 1)  # آخرین پیام خوانده نشده
                        )
            
            # به‌روزرسانی زمان مکالمه
            conversation.updated_at = timezone.now() - timedelta(minutes=30)
            conversation.save()
            
            created_count += 1
            print(f"✅ مکالمه '{conversation.subject}' با {len(conv_data['messages'])} پیام ایجاد شد")
        
        print(f"🎉 {created_count} مکالمه نمونه ایجاد شد")
        
    except Exception as e:
        print(f"❌ خطا در ایجاد مکالمات: {str(e)}")

def create_sample_notifications():
    """ایجاد نوتیفیکیشن‌های نمونه"""
    print("\n🔔 ایجاد نوتیفیکیشن‌های نمونه...")
    
    try:
        users = User.objects.filter(is_active=True)
        
        notifications_data = [
            {
                'notification_type': 'admin_notice',
                'title': 'به‌روزرسانی سیستم',
                'message': 'سیستم پیام‌رسانی جدید راه‌اندازی شد. اکنون می‌توانید با سایر کاربران ارتباط برقرار کنید.',
            },
            {
                'notification_type': 'new_message',
                'title': 'پیام جدید دریافت شد',
                'message': 'پیام جدیدی در مکالمه "سوال درباره پروانه ساختمان" دریافت کردید.',
            },
            {
                'notification_type': 'request_status',
                'title': 'تغییر وضعیت درخواست',
                'message': 'درخواست پروانه ساختمان شما به مرحله بررسی فنی رسید.',
            }
        ]
        
        created_count = 0
        for user in users:
            for notif_data in notifications_data:
                Notification.objects.create(
                    user=user,
                    notification_type=notif_data['notification_type'],
                    title=notif_data['title'],
                    message=notif_data['message'],
                    is_read=False,
                    created_at=timezone.now() - timedelta(hours=created_count % 24)
                )
                created_count += 1
        
        print(f"🎉 {created_count} نوتیفیکیشن نمونه ایجاد شد")
        
    except Exception as e:
        print(f"❌ خطا در ایجاد نوتیفیکیشن‌ها: {str(e)}")

def main():
    """اجرای اصلی"""
    print("🚀 شروع ایجاد داده‌های نمونه پیام‌رسانی...")
    print("="*60)
    
    create_sample_announcements()
    create_sample_conversations()
    create_sample_notifications()
    
    print("\n" + "="*60)
    print("✨ تمام داده‌های نمونه پیام‌رسانی ایجاد شد!")
    print("\n📋 برای تست سیستم:")
    print("1. به آدرس /messaging/ بروید")
    print("2. اطلاعیه‌ها را در /messaging/announcements/ مشاهده کنید")
    print("3. مکالمات را در /messaging/conversations/ ببینید")
    print("4. پیام جدید در /messaging/start/ ارسال کنید")

if __name__ == '__main__':
    main()