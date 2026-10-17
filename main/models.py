
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from decimal import Decimal

from .storage import PrivateStorage

# تقسیمات کشوری ایران
class Province(models.Model):
    """
    استان - Province
    """
    name = models.CharField(max_length=100, unique=True, verbose_name='نام استان')
    code = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name='کد استان')
    capital = models.CharField(max_length=100, null=True, blank=True, verbose_name='مرکز استان')
    
    class Meta:
        verbose_name = 'استان'
        verbose_name_plural = 'استان‌ها'
        ordering = ['name']
    
    def __str__(self):
        return self.name

class County(models.Model):
    """
    شهرستان - County
    """
    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name='counties', verbose_name='استان')
    name = models.CharField(max_length=100, verbose_name='نام شهرستان')
    code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد شهرستان')
    
    class Meta:
        verbose_name = 'شهرستان'
        verbose_name_plural = 'شهرستان‌ها'
        ordering = ['province', 'name']
        unique_together = ['province', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.province.name})"

class District(models.Model):
    """
    بخش - District
    """
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='districts', verbose_name='شهرستان')
    name = models.CharField(max_length=100, verbose_name='نام بخش')
    code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد بخش')
    
    class Meta:
        verbose_name = 'بخش'
        verbose_name_plural = 'بخش‌ها'
        ordering = ['county', 'name']
        unique_together = ['county', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.county.name})"

class Dehestan(models.Model):
    """
    دهستان - Dehestan (Rural District)
    """
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='dehestans', verbose_name='بخش')
    name = models.CharField(max_length=100, verbose_name='نام دهستان')
    code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد دهستان')
    
    class Meta:
        verbose_name = 'دهستان'
        verbose_name_plural = 'دهستان‌ها'
        ordering = ['district', 'name']
        unique_together = ['district', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.district.name})"

class CityVillage(models.Model):
    """
    شهر/روستا - City/Village
    """
    SETTLEMENT_TYPES = [
        ('city', 'شهر'),
        ('village', 'روستا'),
    ]
    
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='settlements', verbose_name='بخش')
    dehestan = models.ForeignKey(Dehestan, on_delete=models.CASCADE, related_name='settlements', null=True, blank=True, verbose_name='دهستان')
    name = models.CharField(max_length=100, verbose_name='نام شهر/روستا')
    settlement_type = models.CharField(max_length=10, choices=SETTLEMENT_TYPES, default='city', verbose_name='نوع')
    code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد')
    population = models.PositiveIntegerField(null=True, blank=True, verbose_name='جمعیت')
    postal_code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد پستی')
    
    # Municipality/Dehyari information
    has_municipality = models.BooleanField(default=False, verbose_name='دارای شهرداری/دهیاری')
    municipality = models.ForeignKey('Municipality', on_delete=models.SET_NULL, null=True, blank=True, related_name='served_areas', verbose_name='شهرداری/دهیاری مربوطه')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ آخرین بروزرسانی')
    
    class Meta:
        verbose_name = 'شهر/روستا'
        verbose_name_plural = 'شهرها/روستاها'
        ordering = ['district', 'settlement_type', 'name']
        unique_together = ['district', 'name']
    
    def __str__(self):
        settlement_type_display = 'شهر' if self.settlement_type == 'city' else 'روستا'
        return f"{self.name} ({settlement_type_display} - {self.district.name})"
    
    @property
    def full_address(self):
        """آدرس کامل شهر/روستا"""
        parts = [
            self.name,
            f"بخش {self.district.name}",
            f"شهرستان {self.district.county.name}",
            f"استان {self.district.county.province.name}"
        ]
        return "، ".join(parts)

class GeographyLink(models.Model):
    """Links to the geography tables, kept in step with the plain-text place columns of the model.

    Migration in stages: (1) these links are filled from the text on every save (text is the source of truth),
    (2) reads move to the links, (3) forms write the links and the text is derived, (4) the text columns go away.
    """
    province_fk = models.ForeignKey('Province', null=True, blank=True, editable=False,
                                    on_delete=models.SET_NULL, related_name='+')
    county_fk = models.ForeignKey('County', null=True, blank=True, editable=False,
                                  on_delete=models.SET_NULL, related_name='+')
    district_fk = models.ForeignKey('District', null=True, blank=True, editable=False,
                                    on_delete=models.SET_NULL, related_name='+')
    city_village_fk = models.ForeignKey('CityVillage', null=True, blank=True, editable=False,
                                        on_delete=models.SET_NULL, related_name='+')

    GEO_TEXT = ('province', 'county', 'district', 'city_village')
    GEO_LINKS = ('province_fk', 'county_fk', 'district_fk', 'city_village_fk')

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None or set(update_fields) & set(self.GEO_TEXT):
            from main.geography import resolve
            found = resolve(*(getattr(self, name) for name in self.GEO_TEXT))
            for name, value in found.items():
                setattr(self, name, value)
            if update_fields is not None:
                kwargs['update_fields'] = list(set(update_fields) | set(self.GEO_LINKS))
        super().save(*args, **kwargs)


class UserProfile(GeographyLink):
    """
    Extended user profile with Persian-specific fields and role management
    """
    USER_ROLES = [
        ('citizen', 'شهروند'),
        ('owner', 'مالک'),
        ('resident', 'ساکن'),
        ('dehyari', 'دهیار'), 
        ('engineer', 'کارشناس دهیاری'),
        ('inspector', 'ناظر فنی'),
        ('accountant', 'مسئول مالی'),
        ('council', 'شورای روستا'),
        ('admin', 'مدیر سیستم'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Persian-specific fields
    national_id = models.CharField(
        max_length=10, 
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r'^\d{10}$', 'کد ملی باید 10 رقم باشد')],
        verbose_name='کد ملی'
    )

    mobile_number = models.CharField(
        max_length=11,
        null=True,
        blank=True,
        validators=[RegexValidator(r'^09\d{9}$', 'شماره موبایل صحیح وارد کنید')],
        verbose_name='شماره موبایل'
    )
    
    father_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='نام پدر'
    )

    # Geographic information
    province = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='استان'
    )
    
    county = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='شهرستان'
    )
    
    district = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='بخش'
    )
    
    city_village = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='شهر/روستا'
    )
    
    # نام شهر یا روستای کاربر
    city_village_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='نام شهر یا روستا'
    )
    
    dehestan_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='نام دهستان'
    )
    
    is_village = models.BooleanField(
        default=False,
        verbose_name='در روستا قرار دارد'
    )

    # Role management
    role = models.CharField(
        max_length=20,
        choices=USER_ROLES,
        default='resident',
        verbose_name='نقش کاربری'
    )

    # Additional fields
    is_verified = models.BooleanField(default=False, verbose_name='تایید شده')
    # Set for accounts a dehyari creates (initial password = national ID); cleared on the first password change.
    must_change_password = models.BooleanField(default=False, verbose_name='نیاز به تغییر رمز')
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name='تاریخ حذف')
    # Original unique values of a deleted account (the live ones are released for a new registration).
    deleted_username = models.CharField(max_length=150, blank=True, default='', editable=False)
    deleted_national_id = models.CharField(max_length=10, blank=True, default='', editable=False)
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'در انتظار تایید'),
            ('approved', 'تایید شده'),
            ('rejected', 'رد شده'),
        ],
        default='approved',
        verbose_name='وضعیت تایید'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'پروفایل کاربری'
        verbose_name_plural = 'پروفایل‌های کاربری'

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_role_display()}"

    def is_staff_member(self):
        """Check if user has staff-level access"""
        return self.role in ['dehyari', 'engineer', 'accountant', 'council', 'admin']

    def is_admin_member(self):
        """Check if user has admin-level access"""
        return self.role in ['admin', 'dehyari']

    def can_manage_users(self):
        """Check if user can manage other users"""
        return self.role in ['admin', 'dehyari']






class Notification(models.Model):
    """
    Model for user notifications
    """
    NOTIFICATION_TYPES = [
        ('request_status', 'تغییر وضعیت درخواست'),
        ('new_message', 'پیام جدید'),
        ('system_update', 'به‌روزرسانی سیستم'),
        ('admin_notice', 'اطلاعیه مدیریت'),
        ('payment_reminder', 'یادآوری پرداخت'),
        ('violation_report', 'گزارش تخلف'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200, verbose_name='عنوان')
    message = models.TextField(verbose_name='پیام')
    is_read = models.BooleanField(default=False, verbose_name='خوانده شده')
    related_request = models.ForeignKey('ServiceRequest', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'اعلان'
        verbose_name_plural = 'اعلان‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.get_full_name()}"

class AutoCADFile(models.Model):
    """
    Model for AutoCAD files uploaded by users
    """
    FILE_TYPES = [
        ('dwg', 'DWG'),
        ('dxf', 'DXF'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'در انتظار پردازش'),
        ('processing', 'در حال پردازش'),
        ('completed', 'پردازش شده'),
        ('failed', 'خطا در پردازش'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='autocad_files')
    original_file = models.FileField(upload_to='autocad_files/', verbose_name='فایل اصلی')
    converted_file = models.FileField(upload_to='dxf_files/', null=True, blank=True, verbose_name='فایل تبدیل شده')
    file_type = models.CharField(max_length=10, choices=FILE_TYPES, verbose_name='نوع فایل')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    upload_date = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ آپلود')
    processed_date = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ پردازش')
    error_message = models.TextField(blank=True, verbose_name='پیام خطا')
    
    class Meta:
        verbose_name = 'فایل اتوکد'
        verbose_name_plural = 'فایل‌های اتوکد'
        ordering = ['-upload_date']
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.file_type} - {self.upload_date}"


class Announcement(models.Model):
    """
    Model for official announcements from village admin
    """
    PRIORITY_CHOICES = [
        ('low', 'کم'),
        ('medium', 'متوسط'),
        ('high', 'بالا'),
        ('urgent', 'فوری'),
    ]

    title = models.CharField(max_length=200, verbose_name='عنوان')
    content = models.TextField(verbose_name='متن اطلاعیه')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', verbose_name='اولویت')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    target_roles = models.JSONField(default=list, verbose_name='نقش‌های هدف')  # List of user roles
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcements')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ انقضا')

    class Meta:
        verbose_name = 'اطلاعیه'
        verbose_name_plural = 'اطلاعیه‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class ViolationReport(models.Model):
    """
    Model for reporting construction violations
    """
    STATUS_CHOICES = [
        ('pending', 'در انتظار بررسی'),
        ('investigating', 'در حال بررسی'),
        ('resolved', 'حل شده'),
        ('dismissed', 'رد شده'),
    ]

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='violation_reports')
    title = models.CharField(max_length=200, verbose_name='عنوان تخلف')
    description = models.TextField(verbose_name='شرح تخلف')
    location_address = models.TextField(verbose_name='آدرس محل تخلف')
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    photo = models.ImageField(upload_to='violation_photos/', verbose_name='تصویر تخلف')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_violations')
    response = models.TextField(blank=True, verbose_name='پاسخ مسئولین')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'گزارش تخلف'
        verbose_name_plural = 'گزارش‌های تخلف'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.reporter.get_full_name()}"

class Suggestion(models.Model):
    """
    Model for suggestions and complaints
    """
    TYPE_CHOICES = [
        ('suggestion', 'پیشنهاد'),
        ('complaint', 'شکایت'),
        ('question', 'سوال'),
        ('request', 'درخواست'),
    ]

    STATUS_CHOICES = [
        ('pending', 'در انتظار بررسی'),
        ('reviewing', 'در حال بررسی'),
        ('responded', 'پاسخ داده شده'),
        ('closed', 'بسته شده'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suggestions')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='نوع')
    subject = models.CharField(max_length=200, verbose_name='موضوع')
    description = models.TextField(verbose_name='شرح')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    response = models.TextField(blank=True, verbose_name='پاسخ')
    responded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='suggestion_responses')
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'پیشنهاد/شکایت'
        verbose_name_plural = 'پیشنهادات و شکایات'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()}: {self.subject}"

class Payment(models.Model):
    """
    Model for tax and fine payments
    """
    PAYMENT_TYPES = [
        ('property_tax', 'مالیات املاک'),
        ('construction_fine', 'جریمه ساختمان'),
        ('permit_fee', 'هزینه مجوز'),
        ('service_fee', 'هزینه خدمات'),
        ('other', 'سایر'),
    ]

    STATUS_CHOICES = [
        ('pending', 'در انتظار پرداخت'),
        ('paid', 'پرداخت شده'),
        ('failed', 'ناموفق'),
        ('refunded', 'بازگشت داده شده'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    property = models.ForeignKey('Property', on_delete=models.SET_NULL, null=True, blank=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES, verbose_name='نوع پرداخت')
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name='مبلغ (تومان)')
    description = models.CharField(max_length=200, verbose_name='شرح')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    receipt_number = models.CharField(max_length=50, unique=True, verbose_name='شماره رسید')
    due_date = models.DateField(verbose_name='مهلت پرداخت')
    paid_date = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ پرداخت')
    installments = models.PositiveIntegerField(default=1, verbose_name='تعداد اقساط')
    current_installment = models.PositiveIntegerField(default=1, verbose_name='قسط فعلی')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'پرداخت'
        verbose_name_plural = 'پرداخت‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_payment_type_display()} - {self.amount:,} تومان"

class EventPermit(models.Model):
    """
    Model for ceremony/event permit requests
    """
    EVENT_TYPES = [
        ('wedding', 'عروسی'),
        ('funeral', 'ختم'),
        ('religious', 'مذهبی'),
        ('cultural', 'فرهنگی'),
        ('sports', 'ورزشی'),
        ('other', 'سایر'),
    ]

    STATUS_CHOICES = [
        ('pending', 'در انتظار بررسی'),
        ('approved', 'تایید شده'),
        ('rejected', 'رد شده'),
        ('completed', 'انجام شده'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_permits')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, verbose_name='نوع مراسم')
    event_name = models.CharField(max_length=200, verbose_name='نام مراسم')
    location = models.TextField(verbose_name='محل برگزاری')
    start_date = models.DateTimeField(verbose_name='تاریخ شروع')
    end_date = models.DateTimeField(verbose_name='تاریخ پایان')
    expected_attendees = models.PositiveIntegerField(verbose_name='تعداد تخمینی شرکت‌کنندگان')
    description = models.TextField(verbose_name='توضیحات')
    contact_person = models.CharField(max_length=100, verbose_name='نام مسئول')
    contact_phone = models.CharField(max_length=11, verbose_name='شماره تماس مسئول')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    permit_number = models.CharField(max_length=50, blank=True, verbose_name='شماره مجوز')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'مجوز مراسم'
        verbose_name_plural = 'مجوزهای مراسم'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_name} - {self.get_event_type_display()}"

class Municipality(GeographyLink):
    """
    Model for municipality/rural council registration
    """
    MUNICIPALITY_TYPES = [
        ('dehyari', 'دهیاری'),
        ('shahrdari', 'شهرداری'),
        ('bakhshdari', 'بخشداری'),
        ('farmandari', 'فرمانداری'),
    ]

    STATUS_CHOICES = [
        ('pending', 'در انتظار تایید'),
        ('active', 'فعال'),
        ('suspended', 'معلق'),
        ('rejected', 'رد شده'),
    ]

    # Basic Information
    name = models.CharField(max_length=200, verbose_name='نام شهرداری/دهیاری')
    municipality_type = models.CharField(max_length=20, choices=MUNICIPALITY_TYPES, verbose_name='نوع')
    province = models.CharField(max_length=100, verbose_name='استان')
    county = models.CharField(max_length=100, verbose_name='شهرستان')
    district = models.CharField(max_length=100, blank=True, verbose_name='بخش')
    city_village = models.CharField(max_length=100, verbose_name='شهر/روستا')
    

    # Contact Information
    official_phone = models.CharField(max_length=11, verbose_name='تلفن رسمی')
    official_email = models.CharField(max_length=254, verbose_name='ایمیل رسمی')
    postal_code = models.CharField(max_length=10, verbose_name='کد پستی')
    address = models.TextField(verbose_name='آدرس کامل')
    
    # Geographic Information
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    
    # Administrative Information
    establishment_date = models.DateField(verbose_name='تاریخ تأسیس')
    population = models.PositiveIntegerField(verbose_name='جمعیت')
    area_hectares = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='مساحت (هکتار)')
    
    # Manager Information
    manager_name = models.CharField(max_length=200, verbose_name='نام مدیر')
    manager_national_id = models.CharField(max_length=10, verbose_name='کد ملی مدیر')
    manager_phone = models.CharField(max_length=11, verbose_name='تلفن مدیر')
    manager_email = models.CharField(max_length=254, verbose_name='ایمیل مدیر')
    
    # System Information
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_municipality')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    license_number = models.CharField(max_length=50, blank=True, verbose_name='شماره پروانه')
    
    # Manager User Account
    manager_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_municipalities', verbose_name='حساب کاربری مدیر')
    
    # Verification Information
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ تایید')
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_municipalities', verbose_name='تایید شده توسط')
    
    # Documents
    governor_decree = models.FileField(upload_to='governor_decrees/', storage=PrivateStorage(), null=True, blank=True, verbose_name='حکم فرماندار')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_municipalities')

    class Meta:
        verbose_name = 'شهرداری/دهیاری'
        verbose_name_plural = 'شهرداری‌ها و دهیاری‌ها'
        unique_together = ['name', 'county', 'city_village']

    def __str__(self):
        return f"{self.get_municipality_type_display()} {self.name} - {self.city_village}"

    def get_full_address(self):
        parts = [self.city_village, self.district, self.county, self.province]
        return ' - '.join([part for part in parts if part])

class LocalBusiness(models.Model):
    """
    Model for local business partnerships
    """
    BUSINESS_TYPES = [
        ('construction', 'مصالح ساختمانی'),
        ('contractor', 'پیمانکار'),
        ('equipment', 'تجهیزات'),
        ('services', 'خدمات'),
        ('supplier', 'تامین‌کننده'),
        ('other', 'سایر'),
    ]

    name = models.CharField(max_length=200, verbose_name='نام کسب‌وکار')
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPES, verbose_name='نوع کسب‌وکار')
    description = models.TextField(verbose_name='توضیحات')
    owner_name = models.CharField(max_length=100, verbose_name='نام مالک')
    phone = models.CharField(max_length=11, verbose_name='شماره تماس')
    address = models.TextField(verbose_name='آدرس')
    municipality = models.ForeignKey(Municipality, on_delete=models.CASCADE, related_name='businesses', null=True, blank=True)
    is_verified = models.BooleanField(default=False, verbose_name='تایید شده')
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, verbose_name='امتیاز')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'کسب‌وکار محلی'
        verbose_name_plural = 'کسب‌وکارهای محلی'
        ordering = ['name']

    def __str__(self):
        return self.name

class FAQ(models.Model):
    """
    Model for frequently asked questions
    """
    CATEGORIES = [
        ('construction', 'ساخت‌وساز'),
        ('legal', 'حقوقی'),
        ('property', 'املاک'),
        ('permits', 'مجوزها'),
        ('payments', 'پرداخت‌ها'),
        ('general', 'عمومی'),
    ]

    category = models.CharField(max_length=20, choices=CATEGORIES, verbose_name='دسته‌بندی')
    question = models.CharField(max_length=500, verbose_name='سوال')
    answer = models.TextField(verbose_name='پاسخ')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    order = models.PositiveIntegerField(default=0, verbose_name='ترتیب نمایش')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سوال متداول'
        verbose_name_plural = 'سوالات متداول'
        ordering = ['category', 'order', 'question']

    def __str__(self):
        return f"{self.get_category_display()}: {self.question[:50]}..."

# Signal to create profile automatically
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile when user is created if it doesn't exist"""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'role': 'citizen',
                'approval_status': 'approved',
                'is_verified': True
            }
        )




class Vote(models.Model):
    """
    Model for council voting on requests
    """
    VOTE_CHOICES = [
        ('approve', 'موافق'),
        ('reject', 'مخالف'),
        ('abstain', 'ممتنع'),
    ]
    
    request = models.ForeignKey('ServiceRequest', on_delete=models.CASCADE, related_name='votes', verbose_name='درخواست')
    council_member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='council_votes', verbose_name='عضو شورا')
    vote = models.CharField(max_length=10, choices=VOTE_CHOICES, verbose_name='رای')
    reason = models.TextField(blank=True, verbose_name='توضیحات')
    voted_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ رای')
    
    class Meta:
        verbose_name = 'رای شورا'
        verbose_name_plural = 'آرای شورا'
        unique_together = ['request', 'council_member']
        ordering = ['-voted_at']
    
    def __str__(self):
        return f"{self.council_member.get_full_name()} - {self.get_vote_display()}"

class CouncilComment(models.Model):
    """
    Model for council member comments on requests
    """
    request = models.ForeignKey('ServiceRequest', on_delete=models.CASCADE, related_name='council_comments', verbose_name='درخواست')
    council_member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='council_member_comments', verbose_name='عضو شورا')
    comment = models.TextField(verbose_name='نظر')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ثبت')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')
    
    class Meta:
        verbose_name = 'نظر شورا'
        verbose_name_plural = 'نظرات شورا'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.council_member.get_full_name()} - {self.request.title[:30]}"

class Conversation(models.Model):
    """
    Model for conversation threads
    """
    subject = models.CharField(max_length=200, verbose_name='موضوع')
    participants = models.ManyToManyField(User, related_name='conversations', verbose_name='شرکت‌کنندگان')
    related_request = models.ForeignKey('ServiceRequest', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='درخواست مرتبط')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین به‌روزرسانی')

    class Meta:
        verbose_name = 'مکالمه'
        verbose_name_plural = 'مکالمات'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.subject}"

class ConversationState(models.Model):
    """
    Per-user mute/archive flags for a conversation
    """
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='user_states', verbose_name='مکالمه')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversation_states', verbose_name='کاربر')
    is_muted = models.BooleanField(default=False, verbose_name='بی‌صدا')
    is_archived = models.BooleanField(default=False, verbose_name='بایگانی شده')

    class Meta:
        verbose_name = 'وضعیت مکالمه'
        verbose_name_plural = 'وضعیت مکالمات'
        unique_together = ['conversation', 'user']

    def __str__(self):
        return f"{self.user} - {self.conversation}"

class Message(models.Model):
    """
    Model for individual messages in a conversation
    """
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages', verbose_name='مکالمه')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages', verbose_name='فرستنده')
    body = models.TextField(verbose_name='متن پیام')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ارسال')

    class Meta:
        verbose_name = 'پیام'
        verbose_name_plural = 'پیام‌ها'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.get_full_name()}: {self.body[:50]}"

class MessageRecipient(models.Model):
    """
    Join table for tracking message read status per recipient
    """
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='recipients', verbose_name='پیام')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_message_status', verbose_name='گیرنده')
    is_read = models.BooleanField(default=False, verbose_name='خوانده شده')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ خواندن')

    class Meta:
        verbose_name = 'وضعیت پیام'
        verbose_name_plural = 'وضعیت پیام‌ها'
        unique_together = ['message', 'recipient']

    def __str__(self):
        return f"{self.recipient.get_full_name()} - {'خوانده' if self.is_read else 'خوانده نشده'}"





class CityVillageRequest(models.Model):
    """
    درخواست افزودن شهر یا روستای جدید به پایگاه داده
    """
    SETTLEMENT_TYPES = [
        ('city', 'شهر'),
        ('village', 'روستا'),
    ]
    STATUS_CHOICES = [
        ('pending', 'در انتظار بررسی'),
        ('approved', 'تایید و اضافه شد'),
        ('rejected', 'رد شده'),
    ]

    province = models.ForeignKey(Province, on_delete=models.CASCADE, verbose_name='استان')
    county = models.ForeignKey(County, on_delete=models.CASCADE, verbose_name='شهرستان')
    district = models.ForeignKey(District, on_delete=models.CASCADE, verbose_name='بخش')
    dehestan = models.ForeignKey(Dehestan, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='دهستان')
    
    name = models.CharField(max_length=100, verbose_name='نام شهر یا روستا')
    settlement_type = models.CharField(max_length=10, choices=SETTLEMENT_TYPES, default='village', verbose_name='نوع')
    requester_name = models.CharField(max_length=100, blank=True, verbose_name='نام درخواست‌دهنده')
    requester_phone = models.CharField(max_length=20, blank=True, verbose_name='شماره تماس')
    description = models.TextField(blank=True, verbose_name='توضیحات تکمیلی')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ درخواست')

    class Meta:
        verbose_name = 'درخواست افزودن شهر/روستا'
        verbose_name_plural = 'درخواست‌های افزودن شهر/روستا'
        ordering = ['-created_at']

    def __str__(self):
        return f"درخواست افزودن {self.name} ({self.get_settlement_type_display()}) - {self.district.name}"

# Office system models (role grants, letters, appointments)
from .models_office import *  # noqa: E402,F401,F403

from .models_accounting import *  # noqa: E402,F401,F403
from .models_finance import *  # noqa: E402,F401,F403
from .models_income import *  # noqa: E402,F401,F403
from .models_payroll import *  # noqa: E402,F401,F403
from .models_council import *  # noqa: E402,F401,F403
from .models_mail import *  # noqa: E402,F401,F403
from .models_gis import *  # noqa: E402,F401,F403
from .models_requests import *  # noqa: E402,F401,F403
from .models_property import *  # noqa: E402,F401,F403


class BlockedIP(models.Model):
    """Client address refused by main.ipblock.BlockedIPMiddleware; managed by admins only."""
    ip = models.GenericIPAddressField(unique=True, verbose_name='نشانی IP')
    reason = models.CharField(max_length=200, blank=True, verbose_name='دلیل')
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class TwoFactorDevice(models.Model):
    """TOTP secret of a user who turned on two-step login (main.twofactor)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='two_factor')
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    last_step = models.BigIntegerField(null=True, blank=True)   # last accepted time step, against replay
    created_at = models.DateTimeField(auto_now_add=True)


class SiteRedirect(models.Model):
    """301/302 redirect managed from the admin server panel (main.siteextras.RedirectMiddleware)."""
    old_path = models.CharField(max_length=300, unique=True, verbose_name='نشانی قدیم')
    new_path = models.CharField(max_length=500, verbose_name='نشانی جدید')
    permanent = models.BooleanField(default=True, verbose_name='دائمی (۳۰۱)')
    hits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['old_path']


class DailyPageView(models.Model):
    """Page views per day and path (main.siteextras.PageViewMiddleware), for the admin stats tab."""
    day = models.DateField()
    path = models.CharField(max_length=200)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['day', 'path'], name='uniq_daily_page_view')]
        indexes = [models.Index(fields=['day'])]
