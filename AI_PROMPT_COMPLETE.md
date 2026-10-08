# پرامپت کامل برای ادامه توسعه پروژه MelkID

## درباره پروژه
من یک **سامانه جامع خدمات شهری و روستایی (MelkID)** دارم که با Django ساخته شده و تا حد زیادی کامل است. این سیستم شامل پنل‌های مختلف برای دهیار، ناظر فنی، کارشناس فنی، کارشناس مالی، شورا و شهروند است.

## وضعیت فعلی پروژه

### ✅ قسمت‌های کامل شده:
- **Backend کامل**: Django framework با تمام مدل‌ها و منطق کسب‌وکار
- **Authentication & Authorization**: سیستم کاربری با 9 نقش مختلف
- **Database Models**: مدل‌های کامل برای املاک، خدمات، پرداخت‌ها، تخلفات
- **امنیت حرفه‌ای**: File validation, Password policy, Security headers
- **Performance بهینه**: Database indexing, Caching (Redis/Local), Logging
- **Error Handling**: Custom middleware, 404/500 pages, Professional logging
- **مستندات کامل**: README, API docs, Deployment guides

### نقش‌های کاربری موجود:
1. **Admin** (مدیر سیستم)
2. **Dehyari** (دهیار/شهردار) 
3. **Council** (شورای روستا)
4. **Engineer** (کارشناس فنی)
5. **Inspector** (ناظر فنی)
6. **Accountant** (مسئول مالی)
7. **Owner** (مالک ملک)
8. **Citizen** (شهروند)
9. **Resident** (ساکن)

### مدل‌های اصلی:
- **UserProfile**: مدیریت کاربران با اطلاعات ایرانی (کد ملی، موبایل، آدرس)
- **Property**: مدیریت املاک و پارسل‌ها
- **ServiceRequest**: درخواست‌های خدمات شهری
- **Payment**: پرداخت‌ها و مالیات
- **ViolationReport**: گزارش تخلفات
- **Notification**: سیستم اطلاع‌رسانی
- **Geographic Models**: Province, County, District, CityVillage

### فایل‌های مهم موجود:
```
melkID/
├── django_project/settings.py    # تنظیمات کامل با امنیت
├── main/models.py                # مدل‌های کامل
├── main/views.py                 # ویوهای کامل
├── main/validators.py            # اعتبارسنجی‌های سفارشی
├── main/middleware.py            # Middleware های حرفه‌ای
├── static/css/                   # CSS فایل‌ها
├── static/js/                    # JavaScript فایل‌ها
├── templates/                    # Template های HTML
├── .env                          # Environment variables
├── requirements.txt              # وابستگی‌های کامل
├── README.md                     # مستندات کامل
└── logs/                         # سیستم لاگ حرفه‌ای
```

## 🎯 هدف: تکمیل قسمت‌های باقی‌مانده

### فاز 1: بهبود UI/UX (اولویت بالا)
- **Mobile Responsiveness**: طراحی واکنش‌گرا برای موبایل و تبلت
- **Loading States**: نمایش وضعیت بارگذاری و spinner ها
- **User Feedback**: پیام‌های موفقیت، خطا، هشدار
- **Navigation**: بهبود منوها و پیمایش
- **Dashboard**: داشبوردهای زیبا برای هر نقش کاربری
- **Form Improvements**: فرم‌های بهتر با validation در frontend
- **Animations**: انیمیشن‌های ملایم و حرفه‌ای

### فاز 2: ویژگی‌های پیشرفته (اولویت متوسط)
- **Real-time Notifications**: اطلاع‌رسانی آنی با WebSocket
- **Advanced Search**: جستجوی پیشرفته و فیلترهای هوشمند
- **File Management**: مدیریت بهتر فایل‌ها و تصاویر
- **Reporting System**: گزارش‌گیری پیشرفته و نمودارها
- **Calendar Integration**: تقویم برای رویدادها و مهلت‌ها
- **Bulk Operations**: عملیات دسته‌ای
- **Export/Import**: خروجی Excel, PDF

### فاز 3: بهینه‌سازی نهایی (اولویت پایین)
- **Performance Optimization**: بهینه‌سازی بیشتر سرعت
- **SEO Optimization**: بهینه‌سازی موتورهای جستجو
- **PWA Features**: تبدیل به Progressive Web App
- **Offline Support**: پشتیبانی آفلاین محدود
- **API Documentation**: مستندات API کامل
- **Testing**: تست‌های خودکار

## 🛠️ تکنولوژی‌های استفاده شده

### Backend:
- **Django 4.2+** (Python web framework)
- **SQLite** (development) / **PostgreSQL** (production)
- **Redis** (caching)
- **Python 3.8+**

### Frontend:
- **HTML5, CSS3, JavaScript**
- **Bootstrap** (احتمالاً)
- **jQuery** (احتمالاً)

### امنیت و Performance:
- **Custom Validators** برای اعتبارسنجی
- **Middleware** های سفارشی
- **Database Indexing** بهینه
- **Logging System** حرفه‌ای
- **File Upload Security**

## 📋 دستورالعمل‌های مهم

### 1. حفظ ساختار موجود
- **هیچ فایل موجودی را حذف نکن**
- **ساختار مدل‌ها را تغییر نده**
- **URL patterns موجود را حفظ کن**
- **نام‌گذاری فارسی را ادامه بده**

### 2. استانداردهای کدنویسی
- **PEP 8** برای Python
- **فارسی** برای متن‌ها و کامنت‌ها
- **RTL Support** برای رابط کاربری
- **Responsive Design** برای موبایل

### 3. امنیت
- **همیشه** input validation انجام بده
- **فایل‌های آپلودی** را بررسی کن
- **CSRF protection** را حفظ کن
- **SQL Injection** را جلوگیری کن

### 4. Performance
- **Database queries** را بهینه کن
- **Static files** را کمپرس کن
- **Caching** را استفاده کن
- **Lazy loading** برای تصاویر

## 🎨 راهنمای طراحی

### رنگ‌بندی:
- **اصلی**: آبی (#007bff)
- **ثانویه**: خاکستری (#6c757d)
- **موفقیت**: سبز (#28a745)
- **خطر**: قرمز (#dc3545)
- **هشدار**: زرد (#ffc107)

### فونت:
- **فارسی**: Vazir, Tahoma
- **انگلیسی**: Arial, sans-serif

### Layout:
- **RTL** برای فارسی
- **Grid System** برای responsive
- **Card-based** design
- **Clean** و **minimal**

## 📝 نمونه کدهای مورد نیاز

### برای UI Components:
```html
<!-- Loading Spinner -->
<div class="loading-spinner">
    <div class="spinner-border text-primary"></div>
    <p>در حال بارگذاری...</p>
</div>

<!-- Success Message -->
<div class="alert alert-success alert-dismissible">
    <i class="fas fa-check-circle"></i>
    عملیات با موفقیت انجام شد
</div>
```

### برای JavaScript:
```javascript
// Loading state management
function showLoading() {
    document.querySelector('.loading-spinner').style.display = 'block';
}

function hideLoading() {
    document.querySelector('.loading-spinner').style.display = 'none';
}

// AJAX with loading
fetch('/api/endpoint/')
    .then(response => response.json())
    .then(data => {
        // Handle success
    })
    .catch(error => {
        // Handle error
    })
    .finally(() => {
        hideLoading();
    });
```

## 🚀 اولویت‌بندی کارها

### فوری (این هفته):
1. **Mobile Responsiveness** - CSS media queries
2. **Loading States** - JavaScript و CSS
3. **User Feedback Messages** - Toast notifications
4. **Navigation Improvements** - Menu و breadcrumb

### مهم (هفته آینده):
1. **Dashboard Improvements** - نمودارها و آمار
2. **Form Enhancements** - Validation و UX
3. **Search Functionality** - فیلتر و جستجو
4. **File Upload UX** - Drag & drop

### آینده (ماه آینده):
1. **Real-time Features** - WebSocket
2. **Advanced Reporting** - Charts و export
3. **Performance Optimization**
4. **Testing & Documentation**

## ⚠️ نکات مهم

1. **همیشه backup** بگیر قبل از تغییرات بزرگ
2. **تست کن** هر تغییری را قبل از commit
3. **مستندات** را به‌روز نگه دار
4. **Git commits** را واضح و فارسی بنویس
5. **Error handling** را فراموش نکن

## 🎯 هدف نهایی

یک **سامانه کامل، زیبا، سریع و کاربرپسند** که:
- در **موبایل** عالی کار کند
- **UX** فوق‌العاده داشته باشد  
- **Performance** بالا داشته باشد
- **امن** و **قابل اعتماد** باشد
- **قابل نگهداری** باشد

---

**سوال**: کدام قسمت را اول شروع کنیم؟ Mobile Responsiveness یا Loading States یا قسمت دیگری؟

**توجه**: لطفاً قبل از شروع، فایل‌های موجود را بررسی کن و ساختار کلی پروژه را درک کن. سپس گام به گام پیش برو.