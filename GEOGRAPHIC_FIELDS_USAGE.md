# راهنمای استفاده از فیلدهای جغرافیایی سلسله‌مراتبی

## نمای کلی

این سیستم امکان انتخاب سلسله‌مراتبی اطلاعات جغرافیایی ایران را فراهم می‌کند:
**استان (Province) > شهرستان (County) > بخش (District) > دهستان (Dehestan)**

## فایل‌های تغییر یافته

### 1. Backend (Django)

#### `main/views.py`
تابع‌های API برای دریافت داده‌های جغرافیایی:
- `api_get_provinces()` - دریافت لیست استان‌ها
- `api_get_counties()` - دریافت شهرستان‌ها بر اساس استان
- `api_get_districts()` - دریافت بخش‌ها بر اساس شهرستان
- `api_get_dehestans()` - دریافت دهستان‌ها بر اساس بخش

#### `main/urls.py`
```python
# Geographic Data API endpoints
path('api/geo/provinces/', views.api_get_provinces, name='api_geo_provinces'),
path('api/geo/counties/', views.api_get_counties, name='api_geo_counties'),
path('api/geo/districts/', views.api_get_districts, name='api_geo_districts'),
path('api/geo/dehestans/', views.api_get_dehestans, name='api_geo_dehestans'),
```

#### `main/forms.py`

**CitizenRegistrationForm** و **ProfileUpdateForm** به‌روز شدند با فیلدهای:
```python
province = forms.ModelChoiceField(...)
county = forms.ModelChoiceField(...)
district = forms.ModelChoiceField(...)
dehestan = forms.ModelChoiceField(...)
```

### 2. Frontend

#### `static/js/geographic_selector.js`
اسکریپت JavaScript برای مدیریت Cascading Dropdowns به صورت خودکار

## نحوه استفاده در Templates

### مرحله 1: اضافه کردن JavaScript

در بالای template خود، اسکریپت را اضافه کنید:

```html
{% load static %}

<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <!-- سایر تگ‌های head -->
    <script src="{% static 'js/geographic_selector.js' %}" defer></script>
</head>
```

### مرحله 2: نمایش فیلدهای جغرافیایی

#### الگوی استاندارد (با ID پیش‌فرض):

```html
<!-- استان -->
<div class="form-group">
    <label for="id_province" class="form-label">استان <span class="text-red-500">*</span></label>
    {{ form.province }}
</div>

<!-- شهرستان -->
<div class="form-group">
    <label for="id_county" class="form-label">شهرستان <span class="text-red-500">*</span></label>
    {{ form.county }}
</div>

<!-- بخش -->
<div class="form-group">
    <label for="id_district" class="form-label">بخش</label>
    {{ form.district }}
</div>

<!-- دهستان -->
<div class="form-group">
    <label for="id_dehestan" class="form-label">دهستان (اختیاری)</label>
    {{ form.dehestan }}
</div>

<!-- چک‌باکس روستا -->
<div class="form-check">
    <input type="checkbox" class="form-check-input" id="id_is_village" name="is_village" {% if form.is_village.value %}checked{% endif %}>
    <label class="form-check-label" for="id_is_village">در روستا قرار دارد</label>
</div>
```

#### الگوی سفارشی (با ID خاص مانند فرم شهروند):

برای فرم‌هایی که از الگوی دیگری استفاده می‌کنند (مثل `id_province_citizen`):

```html
<!-- استان -->
<div class="form-group">
    <label for="id_province_citizen" class="form-label">استان <span class="text-red-500">*</span></label>
    {{ form.province }}
</div>

<!-- شهرستان -->
<div class="form-group">
    <label for="id_county_citizen" class="form-label">شهرستان <span class="text-red-500">*</span></label>
    {{ form.county }}
</div>

<!-- بخش -->
<div class="form-group">
    <label for="id_district_citizen" class="form-label">بخش</label>
    {{ form.district }}
</div>

<!-- دهستان -->
<div class="form-group">
    <label for="id_dehestan_citizen" class="form-label">دهستان (اختیاری)</label>
    {{ form.dehestan }}
</div>
```

### مرحله 3: CSS Classes (اختیاری)

می‌توانید از کلاس‌های Tailwind یا Bootstrap استفاده کنید:

#### Tailwind CSS:
```html
<div class="mb-6">
    <label for="id_province" class="block text-gray-700 font-medium mb-2">
        استان <span class="text-red-500">*</span>
    </label>
    {{ form.province }}
</div>
```

#### Bootstrap:
```html
<div class="mb-3">
    <label for="id_province" class="form-label">
        استان <span class="text-danger">*</span>
    </label>
    {{ form.province }}
</div>
```

## مثال کامل: فرم ثبت‌نام شهروند

```html
{% load static %}
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ثبت‌نام شهروند</title>
    
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- فایل JavaScript برای Cascading Dropdowns -->
    <script src="{% static 'js/geographic_selector.js' %}" defer></script>
</head>
<body class="bg-gray-100">
    
    <div class="container mx-auto p-6">
        <div class="max-w-2xl mx-auto bg-white rounded-lg shadow-lg p-8">
            <h1 class="text-2xl font-bold mb-6">ثبت‌نام شهروند</h1>
            
            <form method="post" class="space-y-6">
                {% csrf_token %}
                
                <!-- بخش اطلاعات شخصی -->
                <div class="border-b pb-6">
                    <h2 class="text-xl font-semibold mb-4">اطلاعات شخصی</h2>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <!-- نام -->
                        <div>
                            <label for="id_first_name" class="block text-gray-700 font-medium mb-2">
                                نام <span class="text-red-500">*</span>
                            </label>
                            {{ form.first_name }}
                        </div>
                        
                        <!-- نام خانوادگی -->
                        <div>
                            <label for="id_last_name" class="block text-gray-700 font-medium mb-2">
                                نام خانوادگی <span class="text-red-500">*</span>
                            </label>
                            {{ form.last_name }}
                        </div>
                        
                        <!-- کد ملی -->
                        <div>
                            <label for="id_national_id" class="block text-gray-700 font-medium mb-2">
                                کد ملی <span class="text-red-500">*</span>
                            </label>
                            {{ form.national_id }}
                        </div>
                        
                        <!-- شماره موبایل -->
                        <div>
                            <label for="id_mobile_number" class="block text-gray-700 font-medium mb-2">
                                شماره موبایل <span class="text-red-500">*</span>
                            </label>
                            {{ form.mobile_number }}
                        </div>
                    </div>
                </div>
                
                <!-- بخش اطلاعات جغرافیایی -->
                <div class="border-b pb-6">
                    <h2 class="text-xl font-semibold mb-4 flex items-center">
                        <i class="fas fa-map-marker-alt text-blue-600 ml-2"></i>
                        اطلاعات محل سکونت
                    </h2>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <!-- استان -->
                        <div>
                            <label for="id_province_citizen" class="block text-gray-700 font-medium mb-2">
                                استان <span class="text-red-500">*</span>
                            </label>
                            {{ form.province }}
                        </div>
                        
                        <!-- شهرستان -->
                        <div>
                            <label for="id_county_citizen" class="block text-gray-700 font-medium mb-2">
                                شهرستان <span class="text-red-500">*</span>
                            </label>
                            {{ form.county }}
                            <p class="text-sm text-gray-500 mt-1">ابتدا استان را انتخاب کنید</p>
                        </div>
                        
                        <!-- بخش -->
                        <div>
                            <label for="id_district_citizen" class="block text-gray-700 font-medium mb-2">
                                بخش
                            </label>
                            {{ form.district }}
                            <p class="text-sm text-gray-500 mt-1">ابتدا شهرستان را انتخاب کنید</p>
                        </div>
                        
                        <!-- دهستان -->
                        <div>
                            <label for="id_dehestan_citizen" class="block text-gray-700 font-medium mb-2">
                                دهستان (اختیاری)
                            </label>
                            {{ form.dehestan }}
                            <p class="text-sm text-gray-500 mt-1">برای مناطق روستایی</p>
                        </div>
                    </div>
                    
                    <!-- چک‌باکس روستا -->
                    <div class="mt-4">
                        <div class="flex items-center">
                            <input type="checkbox" 
                                   id="id_is_village_citizen" 
                                   name="is_village" 
                                   class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500"
                                   {% if form.is_village.value %}checked{% endif %}>
                            <label for="id_is_village_citizen" class="mr-2 text-gray-700">
                                محل سکونت من در روستا است
                            </label>
                        </div>
                    </div>
                </div>
                
                <!-- دکمه ثبت -->
                <div class="flex justify-end">
                    <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-medium transition-colors">
                        <i class="fas fa-check ml-2"></i>
                        ثبت‌نام
                    </button>
                </div>
            </form>
        </div>
    </div>
    
</body>
</html>
```

## نکات مهم

### 1. ID های فیلدها
اسکریپت JavaScript به صورت خودکار فیلدهای با ID های زیر را شناسایی می‌کند:
- **الگوی 1:** `id_province`, `id_county`, `id_district`, `id_dehestan`
- **الگوی 2:** `id_province_citizen`, `id_county_citizen`, `id_district_citizen`, `id_dehestan_citizen`

### 2. فیلدهای Disabled
شهرستان، بخش و دهستان به صورت پیش‌فرض غیرفعال هستند و تنها پس از انتخاب والد خود فعال می‌شوند.

### 3. ذخیره داده‌ها
داده‌ها به صورت **نام** در جدول UserProfile ذخیره می‌شوند:
```python
profile.province = "تهران"
profile.county = "شهریار"
profile.district = "مرکزی"
profile.dehestan_name = "جوقین"
```

### 4. اختیاری بودن
همه فیلدهای جغرافیایی **اختیاری** هستند (`required=False`) اما می‌توانید در validation خود آنها را الزامی کنید.

## عیب‌یابی

### مشکل: Dropdowns کار نمی‌کنند
- بررسی کنید که `geographic_selector.js` به درستی بارگذاری شده است
- Console مرورگر را برای خطاها بررسی کنید
- مطمئن شوید که URLهای API به درستی تنظیم شده‌اند

### مشکل: داده‌ها نمایش داده نمی‌شوند
- بررسی کنید که داده‌های جغرافیایی از طریق `import_geographic_data.py` وارد شده باشند
- دیتابیس را بررسی کنید: `python manage.py dbshell`
  ```sql
  SELECT COUNT(*) FROM main_province;
  SELECT COUNT(*) FROM main_county;
  SELECT COUNT(*) FROM main_district;
  SELECT COUNT(*) FROM main_dehestan;
  ```

### مشکل: CSRF Token Error
مطمئن شوید که `{% csrf_token %}` در فرم وجود دارد.

## دستورات مفید

### وارد کردن داده‌های جغرافیایی
```bash
python import_geographic_data.py
```

### بررسی APIها
```bash
# استان‌ها
curl http://localhost:8000/api/geo/provinces/

# شهرستان‌های استان تهران (فرض کنیم ID=1)
curl http://localhost:8000/api/geo/counties/?province_id=1

# بخش‌های شهرستان شهریار (فرض کنیم ID=10)
curl http://localhost:8000/api/geo/districts/?county_id=10

# دهستان‌های بخش مرکزی (فرض کنیم ID=50)
curl http://localhost:8000/api/geo/dehestans/?district_id=50
```

## سوالات متداول

**Q: آیا می‌توانم IDهای سفارشی استفاده کنم؟**  
A: بله، اسکریپت را تغییر دهید و الگوی جدید را به آرایه `patterns` اضافه کنید.

**Q: چطور می‌توانم داده‌های بیشتری اضافه کنم؟**  
A: فایل `import_geographic_data.py` را ویرایش کرده و داده‌های جدید اضافه کنید.

**Q: آیا می‌توانم از این سیستم در فرم‌های دیگر استفاده کنم؟**  
A: بله! تنها کافی است فیلدهای مشابه را در فرم خود تعریف کرده و اسکریپت را لود کنید.

## پشتیبانی

برای گزارش مشکلات یا درخواست ویژگی‌های جدید، لطفا Issue ایجاد کنید.
