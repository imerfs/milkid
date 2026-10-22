from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.db import transaction
from django.utils import timezone
from functools import wraps
import json
import os

from .common import role_required
from main import lifecycle
from main.office import roles as office_roles
from main.access import policy_required
from main.messaging_views import (
    messaging_dashboard, conversation_list, conversation_detail, 
    start_conversation, create_announcement, announcement_list, 
    announcement_detail, api_unread_count, api_send_quick_message
)
from main.forms import (ContactForm, CustomUserCreationForm, CitizenRegistrationForm, CustomAuthenticationForm, 
                   ServiceRequestForm, ProfileUpdateForm, DocumentUploadForm, ServiceWizardStepForm,
                   MunicipalityRegistrationForm, PropertyRegistrationForm, PropertySearchForm, ConstructionPermitForm,
                   PropertyAdvertisementForm)
from main.models import (UserProfile, ServiceRequest, Notification, RequestDocument, Service, ServiceStep, Property, Municipality,
                   PropertyAdvertisement, AutoCADFile, PropertyData, Payment, Conversation, Message, MessageRecipient,
                   ViolationReport, Inspection, InspectionDocument, TechnicalReport, Province, County, District, CityVillage,
                   Vote, CouncilComment, PropertyAdvertisementEditLog)


@policy_required('mayor.manage')
def dehyari_dashboard(request):
    """Enhanced Dashboard for dehyari (دهیار/شهردار)"""
    from main.models import ViolationReport, Announcement
    
    user_profile = request.user.profile
    
    # Try to get the municipality managed by this user
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
        municipality_filter = Q(user__profile__city_village=municipality.city_village)
    except Municipality.DoesNotExist:
        municipality = None
        municipality_filter = Q(pk__in=[])
    
    # Get recent requests for this municipality
    recent_requests = ServiceRequest.objects.filter(municipality_filter).order_by('-created_at')[:10]
    
    # Get pending requests for quick access
    pending_requests = ServiceRequest.objects.filter(
        municipality_filter, 
        status='pending'
    ).order_by('-created_at')[:5]

    # Requests forwarded to Mayor/Dehyar for final review/approval
    mayor_approval_requests = ServiceRequest.objects.filter(
        municipality_filter,
        Q(workflow_stage='mayor_review') | Q(referral_target='dehyari', status__in=['pending', 'in_review'])
    ).order_by('-referral_date', '-created_at')
    
    # Get staff members
    staff_members_queryset = UserProfile.objects.filter(
        role__in=['engineer', 'inspector', 'accountant'],
        city_village=municipality.city_village if municipality else None
    ).select_related('user')
    
    staff_count = staff_members_queryset.count()
    staff_members = staff_members_queryset[:5]
    
    violations_filter = Q(reporter__profile__city_village=municipality.city_village) if municipality else Q(pk__in=[])

    # Get recent violations
    recent_violations = ViolationReport.objects.filter(
        violations_filter
    ).order_by('-created_at')[:5]
    
    # Get unread notifications
    unread_notifications = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).order_by('-created_at')[:5]
    
    # Statistics
    stats = {
        'total_requests': ServiceRequest.objects.filter(municipality_filter).count(),
        'pending_requests': ServiceRequest.objects.filter(municipality_filter, status='pending').count(),
        'in_review_requests': ServiceRequest.objects.filter(municipality_filter, status='in_review').count(),
        'approved_requests': ServiceRequest.objects.filter(municipality_filter, status='approved').count(),
        'rejected_requests': ServiceRequest.objects.filter(municipality_filter, status='rejected').count(),
        'completed_requests': ServiceRequest.objects.filter(municipality_filter, status='completed').count(),
        'mayor_approval_count': mayor_approval_requests.count(),
        'total_properties': Property.objects.count(),
        'total_violations': ViolationReport.objects.filter(violations_filter).count(),
        'pending_violations': ViolationReport.objects.filter(violations_filter, status='pending').count(),
        'staff_count': staff_count,
        'citizens_count': UserProfile.objects.filter(
            role__in=['citizen', 'owner'],
            city_village=municipality.city_village if municipality else None
        ).count(),
        'unread_notifications': unread_notifications.count(),
    }
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'recent_requests': recent_requests,
        'pending_requests': pending_requests,
        'mayor_approval_requests': mayor_approval_requests,
        'staff_members': staff_members,
        'recent_violations': recent_violations,
        'unread_notifications': unread_notifications,
        'stats': stats,
    }
    return render(request, 'main/dashboards/mayor.html', context)


@policy_required('mayor.manage')
def mayor_staff_list(request):
    """Staff of the village: managed on the roles page (the old list template never existed)."""
    return redirect('main:role_grants')


def _legacy_mayor_staff_list(request):
    """Kept for reference until the roles page fully replaces it."""
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        messages.error(request, 'شهرداری/دهیاری شما یافت نشد.')
        return redirect('main:dehyari_dashboard')
    
    staff = UserProfile.objects.filter(
        city_village=municipality.city_village,
        role__in=office_roles.GRANTABLE
    ).select_related('user').order_by('role', 'user__first_name')
    
    paginator = Paginator(staff, 20)
    page_number = request.GET.get('page')
    staff_list = paginator.get_page(page_number)
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'staff_list': staff_list,
    }
    return render(request, 'main/mayor/staff_list.html', context)



def _password_ok(request, password):
    """Run Django's password validators; report the first problems as messages."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    try:
        validate_password(password or '')
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)
        return False
    return True

@policy_required('mayor.manage')
def mayor_staff_add(request):
    """Add new staff member"""
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        messages.error(request, 'شهرداری/دهیاری شما یافت نشد.')
        return redirect('main:dehyari_dashboard')
    
    if request.method != 'POST':
        return redirect('main:role_grants')       # staff are added by giving a village resident a role

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        national_id = request.POST.get('national_id')
        mobile_number = request.POST.get('mobile_number')
        role = request.POST.get('role')
        
        if role not in office_roles.GRANTABLE:
            messages.error(request, 'نقش انتخاب‌شده معتبر نیست.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'نام کاربری تکراری است.')
        elif UserProfile.objects.filter(national_id=national_id).exists():
            messages.error(request, 'کد ملی تکراری است.')
        elif not _password_ok(request, password):
            pass
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            
            profile = user.profile
            profile.national_id = national_id
            profile.mobile_number = mobile_number
            profile.role = role
            profile.province = municipality.province
            profile.county = municipality.county
            profile.district = municipality.district
            profile.city_village = municipality.city_village
            profile.is_verified = True
            profile.approval_status = 'approved'
            profile.save()
            
            Notification.objects.create(
                user=user,
                notification_type='system_update',
                title='ثبت‌نام موفق',
                message=f'حساب کاربری شما به عنوان {profile.get_role_display()} توسط دهیاری ثبت شد.'
            )
            
            messages.success(request, f'کارمند {first_name} {last_name} با موفقیت اضافه شد.')
            return redirect('main:mayor_staff_list')
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
    }
    return render(request, 'main/mayor/staff_add.html', context)


@policy_required('mayor.manage')
def mayor_staff_edit(request, staff_id):
    """Edit staff member"""
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        messages.error(request, 'شهرداری/دهیاری شما یافت نشد.')
        return redirect('main:dehyari_dashboard')
    
    staff = get_object_or_404(UserProfile, id=staff_id, city_village=municipality.city_village,
                              role__in=office_roles.GRANTABLE)
    
    if request.method == 'POST':
        staff.user.first_name = request.POST.get('first_name', staff.user.first_name)
        staff.user.last_name = request.POST.get('last_name', staff.user.last_name)
        staff.user.email = request.POST.get('email', staff.user.email)
        staff.user.save()
        
        staff.mobile_number = request.POST.get('mobile_number', staff.mobile_number)
        # the role itself changes only through office.roles (validated, recorded, notified)
        staff.is_active = request.POST.get('is_active') == 'on'
        staff.save()
        
        messages.success(request, f'اطلاعات {staff.user.get_full_name()} به‌روزرسانی شد.')
        return redirect('main:mayor_staff_list')
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'staff': staff,
    }
    return render(request, 'main/mayor/staff_edit.html', context)


@policy_required('mayor.manage')
def mayor_staff_delete(request, staff_id):
    """Delete staff member"""
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        messages.error(request, 'شهرداری/دهیاری شما یافت نشد.')
        return redirect('main:dehyari_dashboard')
    
    staff = get_object_or_404(UserProfile, id=staff_id, city_village=municipality.city_village,
                              role__in=office_roles.GRANTABLE)
    
    if request.method == 'POST':
        staff_name = staff.user.get_full_name()
        staff.user.delete()
        messages.success(request, f'کارمند {staff_name} حذف شد.')
        return redirect('main:mayor_staff_list')
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@policy_required('mayor.manage')
def mayor_requests_list(request):
    """List all service requests with filtering and pagination"""
    from main.views.mayor_panel import tab_redirect
    if (moved := tab_redirect(request, 'requests')):
        return moved
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
        municipality_filter = Q(user__profile__city_village=municipality.city_village)
    except Municipality.DoesNotExist:
        municipality = None
        municipality_filter = Q(pk__in=[])   # no municipality: show nothing, never every request
    
    requests_query = ServiceRequest.objects.filter(municipality_filter).select_related('user', 'service', 'assigned_to')
    
    status_filter = request.GET.get('status', '')
    request_type_filter = request.GET.get('request_type', '')
    search_query = request.GET.get('search', '')
    
    if status_filter:
        requests_query = requests_query.filter(status=status_filter)
    if request_type_filter:
        requests_query = requests_query.filter(request_type=request_type_filter)
    if search_query:
        requests_query = requests_query.filter(
            Q(title__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    requests_query = requests_query.order_by('-created_at')
    
    paginator = Paginator(requests_query, 15)
    page_number = request.GET.get('page')
    service_requests = paginator.get_page(page_number)
    
    staff_members = UserProfile.objects.filter(
        role__in=['engineer', 'inspector', 'accountant'],
        city_village=municipality.city_village if municipality else None
    ).select_related('user')
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'service_requests': service_requests,
        'staff_members': staff_members,
        'status_filter': status_filter,
        'request_type_filter': request_type_filter,
        'search_query': search_query,
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'request_type_choices': ServiceRequest.REQUEST_TYPES,
    }
    return render(request, 'main/mayor/requests_list.html', context)


def _managed_municipality(user):
    """Municipality managed by ``user`` (or None)."""
    return Municipality.objects.filter(admin_user=user).first()


def _in_municipality(service_request, municipality):
    """True if the request's owner lives in the municipality's village."""
    return service_request.user.profile.city_village == municipality.city_village



@policy_required('mayor.manage')
def mayor_request_approve(request, request_id):
    """Approve a service request"""
    municipality = _managed_municipality(request.user)
    if municipality is None:
        return JsonResponse({'success': False, 'error': 'Municipality not found'}, status=404)
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    if not _in_municipality(service_request, municipality):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    try:
        lifecycle.approve(service_request, request.user, authority='mayor')
    except lifecycle.TransitionError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    messages.success(request, 'درخواست با موفقیت تایید شد.')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'درخواست تایید شد'})
    return redirect('main:mayor_requests_list')


@policy_required('mayor.manage')
def mayor_request_reject(request, request_id):
    """Reject a service request"""
    municipality = _managed_municipality(request.user)
    if municipality is None:
        return JsonResponse({'success': False, 'error': 'Municipality not found'}, status=404)
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    if request.method != 'POST' or not _in_municipality(service_request, municipality):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    reason = request.POST.get('reason', 'درخواست توسط دهیاری رد شد.')
    try:
        lifecycle.reject(service_request, request.user, reason, authority='mayor')
    except lifecycle.TransitionError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    messages.success(request, 'درخواست رد شد.')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'درخواست رد شد'})
    return redirect('main:mayor_requests_list')


@policy_required('mayor.manage')
def mayor_request_assign(request, request_id):
    """Assign request to staff member"""
    if _managed_municipality(request.user) is None:
        return JsonResponse({'success': False, 'error': 'Municipality not found'}, status=404)
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
    staff_id = request.POST.get('staff_id')
    if staff_id:
        staff_user = get_object_or_404(User, id=staff_id)
        try:
            lifecycle.assign(service_request, request.user, staff_user)
        except lifecycle.TransitionError as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=409)
        messages.success(request, f'درخواست به {staff_user.get_full_name()} ارجاع شد.')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'درخواست ارجاع شد'})
    return redirect('main:mayor_requests_list')


@policy_required('mayor.manage')
def mayor_violations_list(request):
    """List all violations"""
    from main.models import ViolationReport
    
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
        municipality_filter = Q(reporter__profile__city_village=municipality.city_village)
    except Municipality.DoesNotExist:
        municipality = None
        municipality_filter = Q()
    
    violations_query = ViolationReport.objects.filter(municipality_filter).select_related('reporter', 'assigned_to')
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        violations_query = violations_query.filter(status=status_filter)
    
    violations_query = violations_query.order_by('-created_at')
    
    paginator = Paginator(violations_query, 15)
    page_number = request.GET.get('page')
    violations = paginator.get_page(page_number)
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'violations': violations,
        'status_filter': status_filter,
        'status_choices': ViolationReport.STATUS_CHOICES,
    }
    return render(request, 'main/mayor/violations_list.html', context)


@policy_required('mayor.manage')
def mayor_violation_create(request):
    """Create new violation report"""
    from main.models import ViolationReport
    
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        messages.error(request, 'شهرداری/دهیاری شما یافت نشد.')
        return redirect('main:dehyari_dashboard')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        location_address = request.POST.get('location_address')
        photo = request.FILES.get('photo')
        
        violation = ViolationReport.objects.create(
            reporter=request.user,
            title=title,
            description=description,
            location_address=location_address,
            photo=photo,
            status='investigating'
        )
        
        messages.success(request, 'گزارش تخلف با موفقیت ثبت شد.')
        return redirect('main:mayor_violations_list')
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
    }
    return render(request, 'main/mayor/violation_create.html', context)


@policy_required('mayor.manage')
def mayor_violation_update(request, violation_id):
    """Update violation status and response"""
    from main.models import ViolationReport
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Municipality not found'}, status=404)
    
    violation = get_object_or_404(ViolationReport, id=violation_id)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        response = request.POST.get('response', '')
        
        violation.status = status
        violation.response = response
        
        if status == 'resolved':
            violation.resolved_at = timezone.now()
        
        violation.save()
        
        Notification.objects.create(
            user=violation.reporter,
            notification_type='violation_report',
            title='به‌روزرسانی گزارش تخلف',
            message=f'وضعیت گزارش تخلف "{violation.title}" به‌روزرسانی شد: {violation.get_status_display()}'
        )
        
        messages.success(request, 'گزارش تخلف به‌روزرسانی شد.')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'گزارش تخلف به‌روزرسانی شد'})
        return redirect('main:mayor_violations_list')
    
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)


@policy_required('mayor.manage')
def mayor_announcements_list(request):
    """List all announcements"""
    from main.models import Announcement
    
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        municipality = None
    
    announcements = Announcement.objects.filter(created_by=request.user).order_by('-created_at')
    
    paginator = Paginator(announcements, 15)
    page_number = request.GET.get('page')
    announcements_page = paginator.get_page(page_number)
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'announcements': announcements_page,
    }
    return render(request, 'main/mayor/announcements_list.html', context)


@policy_required('mayor.manage')
def mayor_announcement_create(request):
    """Create new announcement"""
    from main.models import Announcement
    
    user_profile = request.user.profile
    
    try:
        municipality = Municipality.objects.get(admin_user=request.user)
    except Municipality.DoesNotExist:
        messages.error(request, 'شهرداری/دهیاری شما یافت نشد.')
        return redirect('main:dehyari_dashboard')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        priority = request.POST.get('priority', 'medium')
        target_roles = request.POST.getlist('target_roles')
        
        if not target_roles:
            target_roles = ['citizen', 'owner']
        
        announcement = Announcement.objects.create(
            title=title,
            content=content,
            priority=priority,
            target_roles=target_roles,
            created_by=request.user
        )
        
        target_users = UserProfile.objects.filter(
            role__in=target_roles,
            city_village=municipality.city_village
        ).select_related('user')
        
        for profile in target_users:
            Notification.objects.create(
                user=profile.user,
                notification_type='admin_notice',
                title=f'اطلاعیه: {title}',
                message=content[:200]
            )
        
        messages.success(request, f'اطلاعیه با موفقیت ثبت و به {target_users.count()} نفر ارسال شد.')
        return redirect('main:mayor_announcements_list')
    
    context = {
        'user_profile': user_profile,
        'municipality': municipality,
        'role_choices': UserProfile.USER_ROLES,
    }
    return render(request, 'main/mayor/announcement_create.html', context)
