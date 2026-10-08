from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, ServiceRequest, RequestDocument, Notification, Service, ServiceStep, Property, ViolationReport, Inspection, InspectionDocument, TechnicalReport, Province, County, District, CityVillage

# Inline admin for UserProfile
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'User Profiles'

# Extended User admin
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'national_id', 'mobile_number', 'role', 'approval_status', 'is_verified', 'created_at']
    list_filter = ['role', 'approval_status', 'is_verified', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'national_id', 'mobile_number']
    actions = ['approve_users', 'reject_users', 'set_pending', 'verify_users', 'unverify_users']

    def approve_users(self, request, queryset):
        updated = queryset.update(approval_status='approved', is_verified=True)
        self.message_user(request, f'{updated} کاربر تایید شد.')
    approve_users.short_description = "✅ تایید کاربران انتخاب شده"

    def reject_users(self, request, queryset):
        updated = queryset.update(approval_status='rejected', is_verified=False)
        self.message_user(request, f'{updated} کاربر رد شد.')
    reject_users.short_description = "❌ رد کاربران انتخاب شده"

    def set_pending(self, request, queryset):
        updated = queryset.update(approval_status='pending', is_verified=False)
        self.message_user(request, f'{updated} کاربر در انتظار تایید قرار گرفت.')
    set_pending.short_description = "⏳ قرار دادن در انتظار تایید"

    def verify_users(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f'{queryset.count()} کاربر تایید شد.')
    verify_users.short_description = "تایید کاربران انتخاب شده"

    def unverify_users(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, f'{queryset.count()} کاربر لغو تایید شد.')
    unverify_users.short_description = "لغو تایید کاربران انتخاب شده"

class ServiceStepInline(admin.TabularInline):
    model = ServiceStep
    extra = 1
    ordering = ['step_number']

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'required_role', 'is_active', 'estimated_duration']
    list_filter = ['category', 'required_role', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ServiceStepInline]

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('name', 'slug', 'description', 'category', 'icon')
        }),
        ('تنظیمات دسترسی', {
            'fields': ('required_role', 'is_active')
        }),
        ('جزئیات خدمت', {
            'fields': ('estimated_duration', 'required_documents')
        }),
    )

@admin.register(ServiceStep)
class ServiceStepAdmin(admin.ModelAdmin):
    list_display = ['service', 'step_number', 'title', 'field_type', 'is_required']
    list_filter = ['field_type', 'is_required', 'service__category']
    search_fields = ['title', 'field_label', 'service__name']
    ordering = ['service', 'step_number']

@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'service', 'request_type', 'status', 'current_step', 'created_at', 'assigned_to']
    list_filter = ['status', 'request_type', 'service', 'created_at', 'assigned_to']
    search_fields = ['title', 'user__username', 'user__first_name', 'user__last_name', 'description']
    raw_id_fields = ['user', 'assigned_to', 'service']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('اطلاعات درخواست', {
            'fields': ('user', 'service', 'title', 'description', 'request_type', 'status', 'current_step')
        }),
        ('اطلاعات ملک', {
            'fields': ('property_address', 'property_area', 'property_usage', 'deed_number', 'parcel_number')
        }),
        ('مدیریت درخواست', {
            'fields': ('assigned_to', 'staff_comments', 'reviewed_at')
        }),
        ('داده‌های فرم', {
            'fields': ('form_data',),
            'classes': ('collapse',)
        }),
    )

@admin.register(RequestDocument)
class RequestDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_name', 'request', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['document_name', 'request__title']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'user__username']
    ordering = ('-created_at',)

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['parcel_number', 'owner_name', 'owner_national_id', 'usage_type', 'area', 'location_area', 'status']
    list_filter = ['usage_type', 'location_area', 'status', 'is_for_sale', 'is_for_rent', 'created_at']
    search_fields = ['parcel_number', 'deed_number', 'owner_name', 'owner_national_id', 'address']
    raw_id_fields = ['created_by']

    fieldsets = (
        ('اطلاعات پایه', {
            'fields': ('parcel_number', 'deed_number', 'address', 'area', 'usage_type', 'location_area')
        }),
        ('اطلاعات مالک', {
            'fields': ('owner_name', 'owner_national_id', 'owner_phone')
        }),
        ('جزئیات ملک', {
            'fields': ('construction_year', 'floors', 'units', 'parking_spaces')
        }),
        ('اطلاعات مالی', {
            'fields': ('assessed_value', 'market_price', 'annual_tax')
        }),
        ('وضعیت و بازار', {
            'fields': ('status', 'is_for_sale', 'is_for_rent')
        }),
        ('موقعیت جغرافیایی', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('متادیتا', {
            'fields': ('created_by',),
            'classes': ('collapse',)
        }),
    )

@admin.register(ViolationReport)
class ViolationReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'reporter', 'status', 'assigned_to', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description', 'location_address']
    raw_id_fields = ['reporter', 'assigned_to']
    date_hierarchy = 'created_at'

@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ['request', 'inspector', 'status', 'is_approved', 'inspection_date', 'created_at']
    list_filter = ['status', 'is_approved', 'created_at']
    search_fields = ['request__title', 'inspector__username', 'report']
    raw_id_fields = ['request', 'inspector']
    date_hierarchy = 'created_at'

@admin.register(InspectionDocument)
class InspectionDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'inspection', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['document_type', 'description']
    raw_id_fields = ['inspection']

@admin.register(TechnicalReport)
class TechnicalReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'engineer', 'report_type', 'request', 'violation', 'created_at']
    list_filter = ['report_type', 'created_at']
    search_fields = ['title', 'content', 'recommendations']
    raw_id_fields = ['request', 'violation', 'engineer']
    date_hierarchy = 'created_at'

# Geographic Models Admin
@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'capital']
    search_fields = ['name', 'code', 'capital']
    ordering = ['name']

@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ['name', 'province', 'code']
    list_filter = ['province']
    search_fields = ['name', 'code', 'province__name']
    ordering = ['province', 'name']

@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ['name', 'county', 'code']
    list_filter = ['county__province', 'county']
    search_fields = ['name', 'code', 'county__name', 'county__province__name']
    ordering = ['county', 'name']

@admin.register(CityVillage)
class CityVillageAdmin(admin.ModelAdmin):
    list_display = ['name', 'settlement_type', 'district', 'has_municipality', 'population', 'created_at']
    list_filter = ['settlement_type', 'has_municipality', 'district__county__province', 'district__county', 'district']
    search_fields = ['name', 'district__name', 'district__county__name', 'district__county__province__name']
    ordering = ['district', 'settlement_type', 'name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('اطلاعات پایه', {
            'fields': ('name', 'settlement_type', 'district', 'dehestan')
        }),
        ('اطلاعات تکمیلی', {
            'fields': ('code', 'population', 'postal_code')
        }),
        ('اطلاعات شهرداری/دهیاری', {
            'fields': ('has_municipality', 'municipality')
        }),
        ('متادیتا', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )