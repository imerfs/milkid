# MelkID - سامانه خدمات شهری و روستایی

سیستم جامع مدیریت املاک و خدمات شهری/روستایی با پشتیبانی کامل از زبان فارسی

## 📋 فهرست مطالب

- [نصب و راه‌اندازی](#نصب-و-راهاندازی)
- [معماری سیستم](#معماری-سیستم)
- [امنیت](#امنیت)
- [عملکرد و بهینه‌سازی](#عملکرد-و-بهینهسازی)
- [توسعه](#توسعه)
- [تست](#تست)
- [استقرار](#استقرار)

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها

- Python 3.8+
- PostgreSQL 12+ (اختیاری - SQLite برای توسعه)
- Redis (اختیاری - برای caching)

### مراحل نصب

1. **کلون کردن پروژه**
```bash
git clone <repository-url>
cd melkID
```

2. **ایجاد محیط مجازی**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\Activate.ps1  # Windows
```

3. **نصب وابستگی‌ها**
```bash
pip install -r requirements.txt
```

4. **تنظیم متغیرهای محیطی**
```bash
cp .env.example .env
# ویرایش فایل .env و تنظیم مقادیر مورد نیاز
```

5. **اجرای Migrations**
```bash
python manage.py migrate
```

6. **ایجاد کاربر مدیر**
```bash
python manage.py createsuperuser
```

7. **اجرای سرور**
```bash
python manage.py runserver
```

سایت در آدرس `http://127.0.0.1:8000` در دسترس خواهد بود.

## 🏗️ معماری سیستم

### ساختار کلی

```
melkID/
├── django_project/      # تنظیمات اصلی پروژه
├── main/               # اپلیکیشن اصلی
│   ├── models.py      # مدل‌های دیتابیس
│   ├── views.py       # ویوها و منطق کسب‌وکار
│   ├── validators.py  # اعتبارسنجی‌های سفارشی
│   └── middleware.py  # Middleware های سفارشی
├── static/            # فایل‌های استاتیک
├── media/             # فایل‌های آپلود شده
├── logs/              # لاگ‌های سیستم
└── tests/             # تست‌های خودکار
```

### مدل‌های اصلی

- **UserProfile**: مدیریت کاربران و نقش‌ها
- **Property**: مدیریت املاک
- **ServiceRequest**: درخواست‌های خدمات
- **Payment**: پرداخت‌ها و مالیات
- **ViolationReport**: گزارش تخلفات

### نقش‌های کاربری

1. **Admin**: مدیر کل سیستم
2. **Dehyari**: دهیار/شهردار
3. **Council**: عضو شورا
4. **Engineer**: کارشناس فنی
5. **Inspector**: ناظر فنی
6. **Accountant**: مسئول مالی
7. **Owner**: مالک ملک
8. **Citizen**: شهروند
9. **Resident**: ساکن

## 🔒 امنیت

### تنظیمات امنیتی

- ✅ Secret Key در environment variables
- ✅ رمزهای عبور با حداقل 8 کاراکتر
- ✅ اعتبارسنجی فایل‌های آپلودی
- ✅ CSRF Protection
- ✅ Security Headers
- ✅ لاگ‌گیری امنیتی

### توصیه‌های امنیتی

1. همیشه DEBUG=False در production
2. استفاده از HTTPS
3. به‌روزرسانی منظم وابستگی‌ها
4. بررسی لاگ‌های امنیتی

## ⚡ عملکرد و بهینه‌سازی

### Caching

سیستم از دو نوع cache پشتیبانی می‌کند:

**Development (Local Memory)**:
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

**Production (Redis)**:
```bash
# نصب Redis
sudo apt-get install redis-server
# فعال‌سازی در .env
USE_REDIS=True
REDIS_URL=redis://localhost:6379/0
```

### Database Indexing

تمام کوئری‌های پرتکرار دارای index هستند:
- UserProfile: role, national_id, city_village
- ServiceRequest: user, status, created_at
- Property: parcel_number, owner_national_id

### Performance Monitoring

سیستم به صورت خودکار درخواست‌های کند (>1 second) را لاگ می‌کند.

## 👨‍💻 توسعه

### Code Style

پروژه از استانداردهای زیر پیروی می‌کند:
- PEP 8 برای Python
- Black برای formatting
- Flake8 برای linting

```bash
# اجرای formatter
black main/

# بررسی code quality
flake8 main/
```

### Pre-commit Hooks

برای بهبود کیفیت کد:

```bash
pip install pre-commit
pre-commit install
```

## 🧪 تست

### اجرای تست‌ها

```bash
# اجرای تمام تست‌ها
pytest

# با coverage
pytest --cov=main --cov-report=html

# تست یک فایل خاص
pytest tests/test_models.py
```

### نوشتن تست

```python
from django.test import TestCase
from main.models import UserProfile

class UserProfileTest(TestCase):
    def test_user_creation(self):
        user = UserProfile.objects.create(...)
        self.assertEqual(user.role, 'citizen')
```

## 📊 Logging

### لاگ‌های موجود

- `logs/django.log`: لاگ‌های عمومی
- `logs/django_errors.log`: خطاها
- `logs/security.log`: لاگ‌های امنیتی

### نحوه استفاده

```python
import logging
logger = logging.getLogger('main')

logger.info('اطلاعات عمومی')
logger.warning('هشدار')
logger.error('خطا', exc_info=True)
```

## 🌐 استقرار (Deployment)

### Production Checklist

- [ ] DEBUG=False
- [ ] SECRET_KEY تصادفی و امن
- [ ] استفاده از PostgreSQL
- [ ] فعال‌سازی Redis
- [ ] HTTPS فعال
- [ ] تنظیم ALLOWED_HOSTS
- [ ] Static files collected
- [ ] Database backup
- [ ] Monitoring فعال

### با Docker

```bash
docker-compose up -d
```

### با Gunicorn

```bash
gunicorn django_project.wsgi:application --bind 0.0.0.0:8000
```

## 📝 مستندات API

مستندات کامل API در آدرس `/api/docs/` در دسترس است.

## 🤝 مشارکت

برای مشارکت در پروژه:

1. Fork کنید
2. یک branch جدید بسازید (`git checkout -b feature/AmazingFeature`)
3. تغییرات را commit کنید (`git commit -m 'Add some AmazingFeature'`)
4. Push کنید (`git push origin feature/AmazingFeature`)
5. Pull Request باز کنید

## 📄 لایسنس

این پروژه تحت لایسنس MIT منتشر شده است.

## 📞 پشتیبانی

برای سوالات و پشتیبانی:
- ایمیل: support@melkid.ir
- تلگرام: @melkid_support

---

**ساخته شده با ❤️ در ایران**
