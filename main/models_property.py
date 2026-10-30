"""Properties and property advertisements (with their images and edit requests)."""
import logging
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models

from .models import AutoCADFile, GeographyLink


class Property(models.Model):
    """
    Model for property/real estate management
    """
    USAGE_TYPES = [
        ('residential', 'مسکونی'),
        ('commercial', 'تجاری'),
        ('agricultural', 'کشاورزی'),
        ('industrial', 'صنعتی'),
        ('mixed', 'مختلط'),
        ('other', 'سایر'),
    ]

    STATUS_CHOICES = [
        ('active', 'فعال'),
        ('pending', 'در انتظار تایید'),
        ('disputed', 'مورد اختلاف'),
        ('archived', 'بایگانی شده'),
    ]

    AREAS = [
        ('center', 'مرکز شهر'),
        ('north', 'شمال شهر'),
        ('south', 'جنوب شهر'),
        ('east', 'شرق شهر'),
        ('west', 'غرب شهر'),
        ('suburban', 'حومه'),
    ]

    # Basic property information
    parcel_number = models.CharField(max_length=50, unique=True, verbose_name='شماره پلاک')
    deed_number = models.CharField(max_length=50, blank=True, verbose_name='شماره سند')
    address = models.TextField(verbose_name='آدرس کامل')
    area = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='مساحت (متر مربع)')
    usage_type = models.CharField(max_length=20, choices=USAGE_TYPES, verbose_name='نوع کاربری')
    location_area = models.CharField(max_length=20, choices=AREAS, verbose_name='منطقه')

    # Owner information
    owner_name = models.CharField(max_length=200, verbose_name='نام مالک')
    owner_national_id = models.CharField(
        max_length=10,
        validators=[RegexValidator(r'^\d{10}$', 'کد ملی باید 10 رقم باشد')],
        verbose_name='کد ملی مالک'
    )
    owner_phone = models.CharField(
        max_length=11,
        validators=[RegexValidator(r'^09\d{9}$', 'شماره موبایل صحیح وارد کنید')],
        blank=True,
        verbose_name='شماره تماس مالک'
    )

    # Property details
    construction_year = models.PositiveIntegerField(null=True, blank=True, verbose_name='سال ساخت')
    floors = models.PositiveIntegerField(default=1, verbose_name='تعداد طبقات')
    units = models.PositiveIntegerField(default=1, verbose_name='تعداد واحد')
    parking_spaces = models.PositiveIntegerField(default=0, verbose_name='تعداد پارکینگ')

    # Financial information
    assessed_value = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name='ارزش کارشناسی (تومان)')
    market_price = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name='قیمت بازار (تومان)')
    annual_tax = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name='مالیات سالانه (تومان)')

    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='وضعیت')
    is_for_sale = models.BooleanField(default=False, verbose_name='در حال فروش')
    is_for_rent = models.BooleanField(default=False, verbose_name='اجاره‌ای')

    # Coordinates (for future map integration)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, verbose_name='عرض جغرافیایی')
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, verbose_name='طول جغرافیایی')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_properties')

    class Meta:
        verbose_name = 'ملک'
        verbose_name_plural = 'املاک'
        ordering = ['parcel_number']

    def __str__(self):
        return f"پلاک {self.parcel_number} - {self.owner_name}"

    @property
    def price(self):
        """Return the most relevant price for display"""
        return self.market_price or self.assessed_value

    def get_area_display_persian(self):
        """Return area with Persian units"""
        return f"{self.area} متر مربع"


class PropertyData(models.Model):
    """
    Model for extracted property data from AutoCAD files
    """
    autocad_file = models.OneToOneField(AutoCADFile, on_delete=models.CASCADE, related_name='property_data')
    
    # مساحت و ابعاد
    area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='مساحت زمین (متر مربع)')
    street_width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name='متراژ معبر (متر)')
    
    # حدود اربعه - شمال
    north_length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='طول شمالی (متر)')
    north_boundary = models.CharField(max_length=200, blank=True, verbose_name='حد شمالی')
    
    # حدود اربعه - جنوب
    south_length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='طول جنوبی (متر)')
    south_boundary = models.CharField(max_length=200, blank=True, verbose_name='حد جنوبی')
    
    # حدود اربعه - شرق
    east_length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='طول شرقی (متر)')
    east_boundary = models.CharField(max_length=200, blank=True, verbose_name='حد شرقی')
    
    # حدود اربعه - غرب
    west_length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='طول غربی (متر)')
    west_boundary = models.CharField(max_length=200, blank=True, verbose_name='حد غربی')
    
    # اطلاعات اضافی
    raw_data = models.JSONField(default=dict, blank=True, verbose_name='داده‌های خام')
    is_verified = models.BooleanField(default=False, verbose_name='تایید شده')
    extraction_date = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ استخراج')
    
    class Meta:
        verbose_name = 'اطلاعات ملک'
        verbose_name_plural = 'اطلاعات املاک'
    
    def __str__(self):
        return f"ملک {self.autocad_file.user.get_full_name()} - مساحت: {self.area or 'نامشخص'}"


class PropertyAdvertisement(GeographyLink):
    """
    Model for property advertisements submitted by users
    """
    AD_TYPES = [
        ('sale', 'فروش'),
        ('rent', 'اجاره'),
        ('both', 'فروش و اجاره'),
    ]
    
    PROPERTY_TYPES = [
        ('residential', 'مسکونی'),
        ('commercial', 'تجاری'),
        ('land', 'زمین'),
        ('agricultural', 'کشاورزی'),
        ('industrial', 'صنعتی'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'در انتظار تایید'),
        ('approved', 'تایید شده'),
        ('rejected', 'رد شده'),
        ('expired', 'منقضی شده'),
    ]
    
    # User and basic info
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='property_ads')
    ad_type = models.CharField(max_length=10, choices=AD_TYPES, verbose_name='نوع آگهی')
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, verbose_name='نوع ملک')
    
    # Property specifications
    total_area = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='مساحت کل')
    built_area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='مساحت زیربنا')
    floors = models.PositiveIntegerField(null=True, blank=True, verbose_name='تعداد طبقات')
    specific_floor = models.PositiveIntegerField(null=True, blank=True, verbose_name='طبقه واحد')
    units = models.PositiveIntegerField(null=True, blank=True, verbose_name='تعداد واحد')
    bedrooms = models.PositiveIntegerField(null=True, blank=True, verbose_name='تعداد اتاق خواب')
    parking = models.PositiveIntegerField(null=True, blank=True, verbose_name='تعداد پارکینگ')
    construction_year = models.PositiveIntegerField(null=True, blank=True, verbose_name='سال ساخت')
    
    # Property features
    parking_available = models.BooleanField(default=False, verbose_name='پارکینگ')
    storage_room = models.BooleanField(default=False, verbose_name='انباری')
    elevator = models.BooleanField(default=False, verbose_name='آسانسور')
    
    # Location
    province = models.CharField(max_length=100, null=True, blank=True, verbose_name='استان')
    county = models.CharField(max_length=100, null=True, blank=True, verbose_name='شهرستان') 
    district = models.CharField(max_length=100, null=True, blank=True, verbose_name='بخش')
    city_village = models.CharField(max_length=100, null=True, blank=True, verbose_name='شهر/روستا')
    is_village = models.BooleanField(default=False, verbose_name='روستا است')
    dehestan = models.CharField(max_length=100, null=True, blank=True, verbose_name='دهستان')
    address = models.TextField(verbose_name='آدرس کامل')
    
    # Pricing
    sale_price = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name='قیمت فروش')
    rent_price = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True, verbose_name='اجاره ماهانه')
    deposit = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name='رهن')
    price_negotiable = models.BooleanField(default=False, verbose_name='قابل مذاکره')
    
    # Description and contact
    description = models.TextField(blank=True, verbose_name='توضیحات')
    contact_name = models.CharField(max_length=200, verbose_name='نام تماس')
    contact_phone = models.CharField(max_length=11, verbose_name='شماره تماس')
    
    # Status and management
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    admin_notes = models.TextField(blank=True, verbose_name='یادداشت مدیر')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_ads')
    
    class Meta:
        verbose_name = 'آگهی ملک'
        verbose_name_plural = 'آگهی‌های املاک'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_ad_type_display()} {self.get_property_type_display()} - {self.contact_name}"
    
    @property
    def pending_edit_requests(self):
        """Check if there are any pending edit requests for this advertisement"""
        return self.edit_logs.filter(status='pending').exists()
    
    def get_pending_edit_count(self):
        """Get count of pending edit requests"""
        return self.edit_logs.filter(status='pending').count()


class PropertyImage(models.Model):
    """
    Model for property advertisement images
    """
    advertisement = models.ForeignKey(PropertyAdvertisement, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='property_ads/', verbose_name='تصویر')
    caption = models.CharField(max_length=200, blank=True, verbose_name='توضیح تصویر')
    is_main = models.BooleanField(default=False, verbose_name='تصویر اصلی')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'تصویر ملک'
        verbose_name_plural = 'تصاویر املاک'
        ordering = ['-is_main', 'uploaded_at']
    
    def __str__(self):
        return f"تصویر {self.advertisement} - {self.caption[:50]}"


class PropertyAdvertisementEditLog(models.Model):
    """
    Model to track edit requests for property advertisements
    """
    STATUS_CHOICES = [
        ('pending', 'در انتظار تایید'),
        ('approved', 'تایید شده'),
        ('rejected', 'رد شده'),
    ]
    
    # Original advertisement and user
    advertisement = models.ForeignKey(PropertyAdvertisement, on_delete=models.CASCADE, related_name='edit_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad_edit_requests')
    
    # Edit data - stores the new values as JSON
    edit_data = models.JSONField(verbose_name='اطلاعات ویرایش شده')
    edit_reason = models.TextField(verbose_name='دلیل ویرایش')
    
    # Status and approval
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='وضعیت')
    admin_notes = models.TextField(blank=True, verbose_name='یادداشت مدیر')
    
    # Users involved in the process
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_ad_edits', verbose_name='بررسی شده توسط')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ درخواست')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ بررسی')
    
    class Meta:
        verbose_name = 'درخواست ویرایش آگهی'
        verbose_name_plural = 'درخواست‌های ویرایش آگهی'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"درخواست ویرایش {self.advertisement} - {self.get_status_display()}"
    
    def apply_changes(self):
        """Apply approved changes to the original advertisement"""
        from django.db import transaction
        from decimal import Decimal, InvalidOperation
        
        if self.status != 'approved':
            return False
            
        # Define allowed fields that can be updated via edit requests
        allowed_fields = {
            # Basic property info
            'ad_type', 'property_type', 'total_area', 'built_area', 'floors', 
            'specific_floor', 'units', 'bedrooms', 'parking', 'construction_year',
            
            # Property features
            'parking_available', 'storage_room', 'elevator',
            
            # Location info
            'province', 'county', 'district', 'city_village', 'is_village', 
            'dehestan', 'address',
            
            # Pricing
            'sale_price', 'rent_price', 'deposit', 'price_negotiable',
            
            # Description and contact
            'description', 'contact_name', 'contact_phone'
        }
        
        # Fields that require special validation
        decimal_fields = {
            'total_area', 'built_area', 'sale_price', 'rent_price', 'deposit'
        }
        
        integer_fields = {
            'floors', 'specific_floor', 'units', 'bedrooms', 'parking', 'construction_year'
        }
        
        boolean_fields = {
            'parking_available', 'storage_room', 'elevator', 'is_village', 'price_negotiable'
        }
        
        choice_fields = {
            'ad_type': dict(PropertyAdvertisement.AD_TYPES).keys(),
            'property_type': dict(PropertyAdvertisement.PROPERTY_TYPES).keys(),
        }
        
        try:
            with transaction.atomic():
                advertisement = self.advertisement
                updated_fields = []
                
                for field, value in self.edit_data.items():
                    # Security check: only allow whitelisted fields
                    if field not in allowed_fields:
                        continue
                        
                    # Verify field exists on model
                    if not hasattr(advertisement, field):
                        continue
                    
                    # Type validation and conversion
                    try:
                        if field in decimal_fields:
                            if value is not None and value != '':
                                value = Decimal(str(value))
                            else:
                                value = None
                                
                        elif field in integer_fields:
                            if value is not None and value != '':
                                value = int(value)
                            else:
                                value = None
                                
                        elif field in boolean_fields:
                            value = bool(value) if value is not None else False
                            
                        elif field in choice_fields:
                            if value not in choice_fields[field]:
                                continue  # Skip invalid choice values
                                
                        elif isinstance(value, str):
                            # String length validation
                            max_lengths = {
                                'contact_phone': 11,
                                'province': 100,
                                'county': 100, 
                                'district': 100,
                                'city_village': 100,
                                'dehestan': 100,
                                'contact_name': 200
                            }
                            if field in max_lengths and len(value) > max_lengths[field]:
                                value = value[:max_lengths[field]]
                                
                    except (ValueError, InvalidOperation, TypeError):
                        # Skip invalid values
                        continue
                    
                    # Apply the change
                    setattr(advertisement, field, value)
                    updated_fields.append(field)
                
                # Save the advertisement if any fields were updated
                if updated_fields:
                    advertisement.save(update_fields=updated_fields + ['updated_at'])
                    return True
                    
        except Exception as e:
            logging.getLogger(__name__).exception('request failed')
            # Log error but don't raise to avoid breaking the approval process
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error applying changes to advertisement {advertisement.id}: خطایی رخ داد؛ دوباره تلاش کنید.")
            return False
            
        return False
