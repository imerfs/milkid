"""Service-request workflow: services, steps, requests, attached documents, inspections and technical reports."""
from django.contrib.auth.models import User
from django.db import models

from .models import UserProfile, ViolationReport


class Service(models.Model):
    """
    Model for defining available services
    """
    SERVICE_CATEGORIES = [
        ('building', 'خدمات ساختمانی'),
        ('property', 'خدمات املاک'),
        ('municipal', 'خدمات شهرداری'),
        ('legal', 'خدمات حقوقی'),
        ('other', 'سایر خدمات'),
    ]

    name = models.CharField(max_length=200, verbose_name='نام خدمت')
    slug = models.SlugField(unique=True, verbose_name='نامک')
    description = models.TextField(verbose_name='توضیحات')
    category = models.CharField(max_length=20, choices=SERVICE_CATEGORIES, verbose_name='دسته‌بندی')
    icon = models.CharField(max_length=50, default='📋', verbose_name='آیکون')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    required_role = models.CharField(
        max_length=20,
        choices=UserProfile.USER_ROLES,
        default='resident',
        verbose_name='نقش مورد نیاز'
    )
    estimated_duration = models.CharField(max_length=50, verbose_name='مدت زمان تخمینی')
    required_documents = models.TextField(verbose_name='مدارک مورد نیاز')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'خدمت'
        verbose_name_plural = 'خدمات'
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class ServiceStep(models.Model):
    """
    Model for defining steps in service request process
    """
    FIELD_TYPES = [
        ('text', 'متن'),
        ('textarea', 'متن چندخطی'),
        ('number', 'عدد'),
        ('email', 'ایمیل'),
        ('file', 'فایل'),
        ('select', 'انتخاب'),
        ('checkbox', 'چک‌باکس'),
        ('date', 'تاریخ'),
    ]

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField(verbose_name='شماره مرحله')
    title = models.CharField(max_length=200, verbose_name='عنوان مرحله')
    description = models.TextField(blank=True, verbose_name='توضیحات')
    field_name = models.CharField(max_length=100, verbose_name='نام فیلد')
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, verbose_name='نوع فیلد')
    field_label = models.CharField(max_length=200, verbose_name='برچسب فیلد')
    field_help_text = models.CharField(max_length=500, blank=True, verbose_name='متن راهنما')
    field_choices = models.TextField(blank=True, verbose_name='گزینه‌ها (جدا شده با کاما)')
    is_required = models.BooleanField(default=True, verbose_name='اجباری')
    validation_regex = models.CharField(max_length=200, blank=True, verbose_name='الگوی اعتبارسنجی')

    class Meta:
        verbose_name = 'مرحله خدمت'
        verbose_name_plural = 'مراحل خدمت'
        ordering = ['service', 'step_number']
        unique_together = ['service', 'step_number']

    def __str__(self):
        return f"{self.service.name} - مرحله {self.step_number}: {self.title}"


class ServiceRequest(models.Model):
    """
    Model for tracking user service requests
    """
    REQUEST_TYPES = [
        ('building_permit', 'صدور پروانه ساختمان'),
        ('no_permit', 'بدون پروانه'),
        ('residence_confirmation', 'تایید سکونت'),
        ('property_deed', 'صدور سند ملک'),
        ('land_use_change', 'تغییر کاربری زمین'),
        ('zoning_inclusion', 'ورود به طرح هادی'),
        ('municipal_services', 'خدمات شهرداری'),
        ('property_services', 'خدمات املاک'),
        ('trash_collection', 'جمع‌آوری زباله'),
        ('equipment_permit', 'مجوز تجهیزات سنگین'),
        ('street_closure', 'مسدود کردن خیابان'),
        ('excavation_permit', 'مجوز حفاری'),
        ('other', 'سایر موارد'),
    ]

    STATUS_CHOICES = [
        ('pending', 'در انتظار بررسی'),
        ('in_review', 'در حال بررسی'),
        ('approved', 'تایید شده'),
        ('rejected', 'رد شده'),
        ('completed', 'تکمیل شده'),
        ('requires_documents', 'نیاز به مدارک'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_requests')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='requests', null=True, blank=True)
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPES, verbose_name='نوع درخواست')
    title = models.CharField(max_length=200, verbose_name='عنوان درخواست')
    description = models.TextField(verbose_name='توضیحات')
    
    # Geographic location fields
    province = models.ForeignKey('Province', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='استان')
    county = models.ForeignKey('County', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='شهرستان')
    district = models.ForeignKey('District', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='بخش')
    city_village = models.ForeignKey('CityVillage', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='شهر/روستا')
    
    property_address = models.TextField(blank=True, verbose_name='آدرس دقیق ملک')

    # Property details
    property_area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='مساحت ملک')
    property_usage = models.CharField(max_length=100, blank=True, verbose_name='کاربری ملک')
    deed_number = models.CharField(max_length=50, blank=True, verbose_name='شماره سند')
    parcel_number = models.CharField(max_length=50, blank=True, verbose_name='شماره پلاک')

    WORKFLOW_STAGES = [
        ('expert_review', 'بررسی کارشناس دهیاری'),
        ('inspection', 'بازرسی و نظارت فنی'),
        ('council_review', 'بررسی و استعلام شورا'),
        ('finance_review', 'محاسبه و پرداخت عوارض'),
        ('mayor_review', 'تایید و امضای دهیار'),
        ('approved', 'تایید نهایی شده'),
        ('rejected', 'رد شده'),
        ('requires_documents', 'نیاز به رفع نقص مدارک'),
    ]

    REFERRAL_TARGETS = [
        ('engineer', 'کارشناس دهیاری'),
        ('inspector', 'ناظر فنی'),
        ('council', 'شورای اسلامی روستا'),
        ('accountant', 'مسئول مالی'),
        ('dehyari', 'دهیار / شهردار'),
    ]

    # Additional request data (JSON field for flexible form data)
    form_data = models.JSONField(default=dict, blank=True, verbose_name='داده‌های فرم')
    current_step = models.PositiveIntegerField(default=1, verbose_name='مرحله فعلی')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')

    # The organization the citizen filed this request with (empty = the village of the citizen's profile).
    target_municipality = models.ForeignKey('Municipality', on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='incoming_requests', verbose_name='سازمان مقصد')

    # Workflow tracking fields
    workflow_stage = models.CharField(
        max_length=30,
        choices=WORKFLOW_STAGES,
        default='expert_review',
        verbose_name='مرحله گردش کار'
    )
    referral_target = models.CharField(
        max_length=30,
        choices=REFERRAL_TARGETS,
        default='engineer',
        blank=True,
        verbose_name='پنل / نقش مقصد فعلی'
    )
    referral_notes = models.TextField(blank=True, verbose_name='دستور / یادداشت ارجاع')
    referral_date = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ ارجاع')
    workflow_history = models.JSONField(default=list, blank=True, verbose_name='تاریخچه گردش کار')

    # Staff handling
    assigned_to = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_requests',
        verbose_name='تخصیص به'
    )
    staff_comments = models.TextField(blank=True, verbose_name='نظرات کارشناس')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def add_workflow_step(self, action, from_user=None, to_role='', notes=''):
        """Helper to append an entry to workflow_history"""
        try:
            import jdatetime
            from django.utils import timezone
            now = timezone.now()
            shamsi_date = jdatetime.datetime.fromgregorian(datetime=now).strftime('%Y/%m/%d %H:%M')
        except Exception:
            from django.utils import timezone
            now = timezone.now()
            shamsi_date = now.strftime('%Y-%m-%d %H:%M')

        entry = {
            'action': action,
            'from_user': from_user.get_full_name() or from_user.username if from_user else 'سیستم',
            'from_role': getattr(from_user.profile, 'role', '') if from_user and hasattr(from_user, 'profile') else '',
            'to_role': to_role,
            'notes': notes or '',
            'date_shamsi': shamsi_date,
            'timestamp': now.isoformat()
        }
        if not isinstance(self.workflow_history, list):
            self.workflow_history = []
        self.workflow_history.append(entry)

    class Meta:
        verbose_name = 'درخواست خدمات'
        verbose_name_plural = 'درخواست‌های خدمات'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_request_type_display()} - {self.user.get_full_name()}"

    def get_status_badge_class(self):
        """Return Bootstrap badge class for status"""
        status_classes = {
            'pending': 'bg-warning',
            'in_review': 'bg-info',
            'approved': 'bg-success',
            'rejected': 'bg-danger',
            'completed': 'bg-primary',
            'requires_documents': 'bg-secondary',
        }
        return status_classes.get(self.status, 'bg-secondary')


class RequestDocument(models.Model):
    """
    Model for documents uploaded with service requests
    """
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='request_documents/')
    document_name = models.CharField(max_length=200, verbose_name='نام سند')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سند درخواست'
        verbose_name_plural = 'اسناد درخواست‌ها'

    def __str__(self):
        return f"{self.document_name} - {self.request.title}"


class Inspection(models.Model):
    """
    Model for property inspections by technical staff
    """
    STATUS_CHOICES = [
        ('pending', 'در انتظار بازرسی'),
        ('in_progress', 'در حال بازرسی'),
        ('completed', 'تکمیل شده'),
        ('rejected', 'رد شده'),
    ]
    
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='inspections', verbose_name='درخواست')
    inspector = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inspections', verbose_name='بازرس')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    
    inspection_date = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ بازرسی')
    report = models.TextField(blank=True, verbose_name='گزارش بازرسی')
    notes = models.TextField(blank=True, verbose_name='یادداشت‌ها')
    
    is_approved = models.BooleanField(default=False, verbose_name='تایید شده')
    rejection_reason = models.TextField(blank=True, verbose_name='دلیل رد')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین به‌روزرسانی')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ تکمیل')
    
    class Meta:
        verbose_name = 'بازرسی'
        verbose_name_plural = 'بازرسی‌ها'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"بازرسی {self.request.title} - {self.inspector.get_full_name()}"


class InspectionDocument(models.Model):
    """
    Model for documents uploaded during inspections
    """
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name='documents', verbose_name='بازرسی')
    document = models.FileField(upload_to='inspection_documents/', verbose_name='فایل')
    document_type = models.CharField(max_length=100, verbose_name='نوع سند')
    description = models.TextField(blank=True, verbose_name='توضیحات')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ آپلود')
    
    class Meta:
        verbose_name = 'سند بازرسی'
        verbose_name_plural = 'اسناد بازرسی'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.document_type} - {self.inspection}"


class TechnicalReport(models.Model):
    """
    Model for technical reports submitted by engineers
    """
    REPORT_TYPES = [
        ('inspection', 'گزارش بازرسی'),
        ('violation', 'گزارش تخلف'),
        ('technical_review', 'بررسی فنی'),
        ('approval', 'گزارش تایید'),
        ('other', 'سایر'),
    ]
    
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='technical_reports', verbose_name='درخواست')
    violation = models.ForeignKey(ViolationReport, on_delete=models.CASCADE, null=True, blank=True, related_name='technical_reports', verbose_name='تخلف')
    engineer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='technical_reports', verbose_name='کارشناس')
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES, verbose_name='نوع گزارش')
    title = models.CharField(max_length=200, verbose_name='عنوان گزارش')
    content = models.TextField(verbose_name='محتوای گزارش')
    recommendations = models.TextField(blank=True, verbose_name='توصیه‌ها')
    
    document = models.FileField(upload_to='technical_reports/', null=True, blank=True, verbose_name='فایل گزارش')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ثبت')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')
    
    class Meta:
        verbose_name = 'گزارش فنی'
        verbose_name_plural = 'گزارش‌های فنی'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.engineer.get_full_name()}"
