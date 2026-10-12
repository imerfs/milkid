from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
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
from main import municipality_approval
from main.accounts import soft_delete_user
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
from django.views.decorators.csrf import ensure_csrf_cookie
from main.models import (UserProfile, ServiceRequest, Notification, RequestDocument, Service, ServiceStep, Property, Municipality,
                   PropertyAdvertisement, AutoCADFile, PropertyData, Payment, Conversation, Message, MessageRecipient,
                   ViolationReport, Inspection, InspectionDocument, TechnicalReport, Province, County, District, CityVillage,
                   Vote, CouncilComment, PropertyAdvertisementEditLog)


@policy_required('admin.manage')
@login_required
@ensure_csrf_cookie
def admin_dashboard(request):
    """Enhanced dashboard for administrators"""
    user_profile = request.user.profile
    from datetime import datetime, timedelta
    import json
    
    # Handle POST requests
    if request.method == 'POST':
        action_type = request.POST.get('action_type', 'user')

        if action_type == 'property_ad':
            ad_id = request.POST.get('ad_id')
            action = request.POST.get('action')
            admin_notes = request.POST.get('admin_notes', '')

            try:
                ad = PropertyAdvertisement.objects.get(id=ad_id)
                if action == 'approve':
                    ad.status = 'approved'
                    ad.approved_at = timezone.now()
                    ad.approved_by = request.user
                    ad.admin_notes = admin_notes or 'آگهی توسط مدیر سیستم تایید شد.'
                    ad.save()

                    Notification.objects.create(
                        user=ad.user,
                        notification_type='system_update',
                        title='آگهی ملک شما تایید شد',
                        message=f'آگهی ملک {ad.get_property_type_display()} شما در {ad.city_village or ad.county or "سیستم"} تایید و منتشر شد.'
                    )
                    messages.success(request, f'آگهی {ad.get_property_type_display()} با موفقیت تایید و منتشر شد.')

                elif action == 'reject':
                    ad.status = 'rejected'
                    ad.admin_notes = admin_notes or 'آگهی توسط مدیر رد شد.'
                    ad.save()

                    Notification.objects.create(
                        user=ad.user,
                        notification_type='system_update',
                        title='آگهی ملک شما رد شد',
                        message=f'آگهی ملک {ad.get_property_type_display()} شما رد شد. علت: {ad.admin_notes}'
                    )
                    messages.warning(request, f'آگهی {ad.get_property_type_display()} رد شد.')

                elif action == 'delete':
                    ad.delete()
                    messages.success(request, 'آگهی با موفقیت حذف گردید.')

            except PropertyAdvertisement.DoesNotExist:
                messages.error(request, 'آگهی مورد نظر یافت نشد.')

            return redirect('main:admin_dashboard')

        elif action_type == 'municipality':
            municipality_id = request.POST.get('municipality_id')
            action = request.POST.get('action')

            try:
                municipality = Municipality.objects.get(id=municipality_id)
                if action == 'approve':
                    municipality_approval.approve(municipality, request.user)
                    messages.success(request, f'درخواست {municipality.name} تایید شد و به سامانه پیوست.')

                elif action == 'reject':
                    municipality.status = 'rejected'
                    municipality.save()

                    if municipality.admin_user:
                        municipality.admin_user.is_active = False
                        municipality.admin_user.save()

                    messages.warning(request, f'درخواست {municipality.name} رد شد.')

            except Municipality.DoesNotExist:
                messages.error(request, 'شهرداری/دهیاری مورد نظر یافت نشد.')

            return redirect('main:admin_dashboard')

        else:
            user_id = request.POST.get('user_id')
            action = request.POST.get('action')

            try:
                user_profile_target = UserProfile.objects.get(id=user_id)
                user_name = user_profile_target.user.get_full_name() or user_profile_target.user.username

                if action == 'approve':
                    user_profile_target.approval_status = 'approved'
                    user_profile_target.is_verified = True
                    user_profile_target.user.is_active = True
                    user_profile_target.user.save()
                    user_profile_target.save()

                    if user_profile_target.role == 'dehyari':
                        messages.success(request, f'دهیار {user_name} تایید شد و به پنل دهیاری دسترسی پیدا کرد.')
                    else:
                        messages.success(request, f'کاربر {user_name} تایید شد و فعال گردید.')

                elif action == 'reject':
                    user_profile_target.approval_status = 'rejected'
                    user_profile_target.user.is_active = False
                    user_profile_target.user.save()
                    user_profile_target.save()
                    messages.warning(request, f'درخواست {user_name} رد شد.')

                elif action in ['block', 'freeze']:
                    if user_profile_target.user == request.user or user_profile_target.user.is_superuser:
                        messages.error(request, 'امکان مسدودسازی حساب کاربری مدیر یا سوپریوزر وجود ندارد.')
                    else:
                        user_profile_target.is_active = False
                        user_profile_target.user.is_active = False
                        user_profile_target.user.save()
                        user_profile_target.save()
                        from django.core.cache import cache
                        cache.delete(f'user_last_seen_{user_profile_target.user.id}')
                        messages.warning(request, f'دسترسی کاربر {user_name} به سامانه مسدود شد.')

                elif action in ['unblock', 'unfreeze', 'activate']:
                    user_profile_target.is_active = True
                    user_profile_target.user.is_active = True
                    user_profile_target.user.save()
                    user_profile_target.save()
                    messages.success(request, f'دسترسی کاربر {user_name} مجدداً فعال و باز گردید.')

                elif action == 'delete':
                    if user_profile_target.user == request.user or user_profile_target.user.is_superuser:
                        messages.error(request, 'امکان حذف حساب کاربری مدیر ارشد یا حساب جاری وجود ندارد.')
                    else:
                        soft_delete_user(user_profile_target.user)
                        messages.success(request, f'کاربر «{user_name}» با موفقیت از سیستم حذف گردید.')

                elif action == 'toggle_access':
                    if user_profile_target.user == request.user or user_profile_target.user.is_superuser:
                        messages.error(request, 'امکان تغییر دسترسی حساب کاربری مدیر یا سوپریوزر وجود ندارد.')
                    else:
                        current_status = bool(user_profile_target.is_active and user_profile_target.user.is_active)
                        new_status = not current_status
                        user_profile_target.is_active = new_status
                        user_profile_target.user.is_active = new_status
                        user_profile_target.user.save()
                        user_profile_target.save()
                        if not new_status:
                            from django.core.cache import cache
                            cache.delete(f'user_last_seen_{user_profile_target.user.id}')
                            messages.warning(request, f'دسترسی کاربر {user_name} مسدود شد.')
                        else:
                            messages.success(request, f'دسترسی کاربر {user_name} فعال شد.')

            except UserProfile.DoesNotExist:
                messages.error(request, 'کاربر یافت نشد.')

            return redirect('main:admin_dashboard')

    # Get requests by status for overview
    request_stats = ServiceRequest.objects.values('status').annotate(count=Count('status'))

    # Recent system activity
    recent_requests = ServiceRequest.objects.all().order_by('-created_at')[:10]

    # User monitoring & access control
    from django.core.cache import cache
    all_profiles_qs = UserProfile.objects.select_related('user').filter(deleted_at__isnull=True).order_by('-user__date_joined')
    now = timezone.now()

    all_users_list = []
    online_users_count = 0
    active_users_count = 0
    blocked_users_count = 0

    role_distribution = {
        'citizen': 0,
        'dehyari': 0,
        'council': 0,
        'engineer': 0,
        'inspector': 0,
        'accountant': 0,
        'admin': 0,
        'other': 0,
    }

    for prof in all_profiles_qs:
        u = prof.user
        last_seen = cache.get(f'user_last_seen_{u.id}')
        
        # Determine online status
        is_online = False
        if u.id == request.user.id:
            is_online = True
            cache.set(f'user_last_seen_{u.id}', now.isoformat(), 300)
        elif last_seen:
            is_online = True
        elif u.last_login and (now - u.last_login).total_seconds() < 300:
            is_online = True

        if is_online:
            online_users_count += 1

        is_user_active = bool(u.is_active and prof.is_active)
        if is_user_active:
            active_users_count += 1
        else:
            blocked_users_count += 1

        # Role counts
        r = prof.role
        if r in role_distribution:
            role_distribution[r] += 1
        elif r in ['resident', 'owner']:
            role_distribution['citizen'] += 1
        else:
            role_distribution['other'] += 1

        all_users_list.append({
            'profile': prof,
            'user': u,
            'is_online': is_online,
            'is_active': is_user_active,
            'can_toggle': not (u.is_superuser or u.id == request.user.id),
        })

    # Pending users for quick review
    pending_users = [item['profile'] for item in all_users_list if item['profile'].approval_status == 'pending']

    # User statistics
    pending_verifications = len(pending_users)
    pending_dehyari = sum(1 for item in all_users_list if item['profile'].approval_status == 'pending' and item['profile'].role == 'dehyari')
    pending_council = sum(1 for item in all_users_list if item['profile'].approval_status == 'pending' and item['profile'].role == 'council')
    total_users = len(all_users_list)
    staff_count = sum(1 for item in all_users_list if item['profile'].role in ['dehyari', 'admin', 'engineer', 'council', 'inspector', 'accountant'])
    frozen_users = blocked_users_count

    # Municipality statistics & data
    municipalities_all = Municipality.objects.all().order_by('-created_at')
    pending_municipalities_list = municipalities_all.filter(status='pending')
    approved_municipalities_list = municipalities_all.filter(status='active')
    rejected_municipalities_list = municipalities_all.filter(status='rejected')

    pending_municipalities = pending_municipalities_list.count()
    approved_municipalities = approved_municipalities_list.count()
    rejected_municipalities = rejected_municipalities_list.count()
    total_municipalities = municipalities_all.count()

    # Property advertisement statistics
    all_property_ads = PropertyAdvertisement.objects.all().order_by('-created_at')
    pending_ads_qs = all_property_ads.filter(status='pending')
    approved_ads_qs = all_property_ads.filter(status='approved')
    rejected_ads_qs = all_property_ads.filter(status='rejected')
    pending_edits_qs = PropertyAdvertisementEditLog.objects.filter(status='pending').order_by('-created_at')

    # Property statistics
    total_properties = Property.objects.count()

    # Get all services
    all_services = Service.objects.all()
    active_services = Service.objects.filter(is_active=True).count()

    # Chart data for monthly requests (last 6 months)
    chart_labels = []
    chart_data = []
    for i in range(5, -1, -1):
        date = timezone.now() - timedelta(days=30*i)
        month_name = date.strftime('%B')[:3]
        count = ServiceRequest.objects.filter(
            created_at__month=date.month,
            created_at__year=date.year
        ).count()
        chart_labels.append(month_name)
        chart_data.append(count)

    # System statistics
    stats = {
        'pending_verifications': pending_verifications,
        'pending_dehyari': pending_dehyari,
        'pending_council': pending_council,
        'total_users': total_users,
        'online_users': online_users_count,
        'active_users': active_users_count,
        'blocked_users': blocked_users_count,
        'staff_count': staff_count,
        'frozen_users': frozen_users,
        'total_requests': ServiceRequest.objects.count(),
        'pending_requests': ServiceRequest.objects.filter(status='pending').count(),
        'approved_requests': ServiceRequest.objects.filter(status='approved').count(),
        'rejected_requests': ServiceRequest.objects.filter(status='rejected').count(),
        'pending_municipalities': pending_municipalities,
        'approved_municipalities': approved_municipalities,
        'rejected_municipalities': rejected_municipalities,
        'total_municipalities': total_municipalities,
        'total_ads': all_property_ads.count(),
        'pending_ads': pending_ads_qs.count(),
        'approved_ads': approved_ads_qs.count(),
        'rejected_ads': rejected_ads_qs.count(),
        'pending_edits': pending_edits_qs.count(),
        'total_properties': total_properties,
        'active_services': active_services,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }

    context = {
        'user_profile': user_profile,
        'stats': stats,
        'request_stats': request_stats,
        'recent_requests': recent_requests,
        'pending_users': pending_users,
        'all_users_list': all_users_list,
        'role_distribution': role_distribution,
        'online_users_count': online_users_count,
        'active_users_count': active_users_count,
        'blocked_users_count': blocked_users_count,
        'all_services': all_services,
        'property_ads': all_property_ads[:100],
        'pending_property_ads': pending_ads_qs,
        'approved_property_ads': approved_ads_qs,
        'rejected_property_ads': rejected_ads_qs,
        'pending_edits': pending_edits_qs,
        'municipalities_all': municipalities_all,
        'pending_municipalities_list': pending_municipalities_list,
        'approved_municipalities_list': approved_municipalities_list,
        'rejected_municipalities_list': rejected_municipalities_list,
    }

    return render(request, 'main/dashboards/admin_dashboard.html', context)



@policy_required('admin.manage')
def manage_property_ads(request):
    """مدیریت آگهی‌های املاک کاربران"""
    from main.models import PropertyAdvertisementEditLog
    from django.utils import timezone
    
    # Handle POST requests for ad approval/rejection and edit approvals
    if request.method == 'POST':
        action_type = request.POST.get('action_type', 'ad')  # 'ad' or 'edit'
        action = request.POST.get('action')
        admin_notes = request.POST.get('admin_notes', '')
        
        if action_type == 'ad':
            # Handle original ad approvals
            ad_id = request.POST.get('ad_id')
            try:
                ad = PropertyAdvertisement.objects.get(id=ad_id)
                
                if action == 'approve':
                    ad.status = 'approved'
                    ad.admin_notes = admin_notes or 'آگهی توسط مدیر تایید شد.'
                    ad.approved_at = timezone.now()
                    ad.approved_by = request.user
                    ad.save()
                    messages.success(request, f'آگهی {ad.get_property_type_display()} تایید شد.')
                    
                elif action == 'reject':
                    ad.status = 'rejected'
                    ad.admin_notes = admin_notes or 'آگهی توسط مدیر رد شد.'
                    ad.save()
                    messages.warning(request, f'آگهی {ad.get_property_type_display()} رد شد.')
                    
            except PropertyAdvertisement.DoesNotExist:
                messages.error(request, 'آگهی یافت نشد.')
        
        elif action_type == 'edit':
            # Handle edit request approvals
            edit_id = request.POST.get('edit_id')
            try:
                edit_log = PropertyAdvertisementEditLog.objects.get(id=edit_id)
                
                if action == 'approve':
                    # Apply the changes to the original advertisement
                    if edit_log.apply_changes():
                        edit_log.status = 'approved'
                        edit_log.admin_notes = admin_notes or 'تغییرات توسط مدیر تایید شد.'
                        edit_log.reviewed_by = request.user
                        edit_log.reviewed_at = timezone.now()
                        edit_log.save()
                        
                        # Create notification for user
                        Notification.objects.create(
                            user=edit_log.user,
                            notification_type='request_status',
                            title='درخواست ویرایش تایید شد',
                            message=f'درخواست ویرایش آگهی {edit_log.advertisement.get_property_type_display()} شما تایید شد.',
                        )
                        
                        messages.success(request, 'درخواست ویرایش تایید شد و تغییرات اعمال گردید.')
                    else:
                        messages.error(request, 'خطا در اعمال تغییرات.')
                        
                elif action == 'reject':
                    edit_log.status = 'rejected'
                    edit_log.admin_notes = admin_notes or 'درخواست ویرایش توسط مدیر رد شد.'
                    edit_log.reviewed_by = request.user
                    edit_log.reviewed_at = timezone.now()
                    edit_log.save()
                    
                    # Create notification for user
                    Notification.objects.create(
                        user=edit_log.user,
                        notification_type='request_status',
                        title='درخواست ویرایش رد شد',
                        message=f'درخواست ویرایش آگهی {edit_log.advertisement.get_property_type_display()} شما رد شد.',
                    )
                    
                    messages.warning(request, 'درخواست ویرایش رد شد.')
                    
            except PropertyAdvertisementEditLog.DoesNotExist:
                messages.error(request, 'درخواست ویرایش یافت نشد.')
            
        return redirect('main:manage_property_ads')
    
    # Get property advertisements by status
    pending_ads = PropertyAdvertisement.objects.filter(status='pending').order_by('-created_at')
    approved_ads = PropertyAdvertisement.objects.filter(status='approved').order_by('-updated_at')[:10]
    rejected_ads = PropertyAdvertisement.objects.filter(status='rejected').order_by('-updated_at')[:10]
    
    # Get pending edit requests
    pending_edits = PropertyAdvertisementEditLog.objects.filter(status='pending').order_by('-created_at')
    
    # Statistics
    stats = {
        'total_ads': PropertyAdvertisement.objects.count(),
        'pending_ads': PropertyAdvertisement.objects.filter(status='pending').count(),
        'approved_ads': PropertyAdvertisement.objects.filter(status='approved').count(),
        'rejected_ads': PropertyAdvertisement.objects.filter(status='rejected').count(),
        'expired_ads': PropertyAdvertisement.objects.filter(status='expired').count(),
        'pending_edits': PropertyAdvertisementEditLog.objects.filter(status='pending').count(),
    }
    
    context = {
        'pending_ads': pending_ads,
        'approved_ads': approved_ads,
        'rejected_ads': rejected_ads,
        'pending_edits': pending_edits,
        'stats': stats,
    }
    return render(request, 'main/admin/manage_property_ads.html', context)


@policy_required('admin.manage')
def manage_users(request):
    """Enhanced user management for administrators"""
    # Get users by categories
    pending_users = UserProfile.objects.filter(approval_status='pending', deleted_at__isnull=True).order_by('-created_at')
    all_users = UserProfile.objects.exclude(role='admin').filter(deleted_at__isnull=True).order_by('-created_at')

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')

        try:
            user_profile = UserProfile.objects.get(id=user_id)
            user_name = user_profile.user.get_full_name()

            if action == 'approve':
                # Approve pending user
                user_profile.approval_status = 'approved'
                user_profile.is_verified = True
                user_profile.user.is_active = True
                user_profile.user.save()
                user_profile.save()
                
                if user_profile.role == 'dehyari':
                    messages.success(request, f'دهیار {user_name} تایید شد و به پنل دهیاری دسترسی پیدا کرد.')
                else:
                    messages.success(request, f'کاربر {user_name} تایید شد و فعال گردید.')

            elif action == 'reject':
                # Reject pending user
                user_profile.approval_status = 'rejected'
                user_profile.user.is_active = False
                user_profile.user.save()
                user_profile.save()
                messages.warning(request, f'درخواست {user_name} رد شد.')

            elif action == 'freeze':
                # Freeze user account
                user_profile.is_active = False
                user_profile.user.is_active = False
                user_profile.user.save()
                user_profile.save()
                messages.warning(request, f'حساب کاربری {user_name} مسدود شد.')

            elif action == 'unfreeze':
                # Unfreeze user account
                user_profile.is_active = True
                user_profile.user.is_active = True
                user_profile.user.save()
                user_profile.save()
                messages.success(request, f'حساب کاربری {user_name} فعال شد.')

            elif action == 'delete':
                soft_delete_user(user_profile.user)
                messages.info(request, f'کاربر {user_name} حذف شد.')

        except UserProfile.DoesNotExist:
            messages.error(request, 'کاربر یافت نشد.')

        return redirect('main:manage_users')

    # Get paginated users
    from django.core.paginator import Paginator
    paginator = Paginator(all_users, 20)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)

    context = {
        'pending_users': pending_users,
        'all_users': users_page,
    }
    return render(request, 'main/manage_users.html', context)


@policy_required('admin.manage')
def manage_requests(request):
    """Manage service requests"""
    # Get all requests with filters
    status_filter = request.GET.get('status', 'all')
    
    if status_filter == 'all':
        requests = ServiceRequest.objects.all()
    else:
        requests = ServiceRequest.objects.filter(status=status_filter)
    
    requests = requests.order_by('-created_at')

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(requests, 20)
    page_number = request.GET.get('page')
    requests_page = paginator.get_page(page_number)

    # Statistics
    stats = {
        'total': ServiceRequest.objects.count(),
        'pending': ServiceRequest.objects.filter(status='pending').count(),
        'in_review': ServiceRequest.objects.filter(status='in_review').count(),
        'approved': ServiceRequest.objects.filter(status='approved').count(),
        'rejected': ServiceRequest.objects.filter(status='rejected').count(),
        'completed': ServiceRequest.objects.filter(status='completed').count(),
    }

    context = {
        'requests': requests_page,
        'stats': stats,
        'current_filter': status_filter,
    }
    return render(request, 'main/manage_requests.html', context)


@policy_required('admin.manage')
def manage_municipalities(request):
    """Admin view for managing municipality applications"""
    municipalities = Municipality.objects.filter(status='pending').order_by('-created_at')
    
    if request.method == 'POST':
        municipality_id = request.POST.get('municipality_id')
        action = request.POST.get('action')
        
        try:
            municipality = Municipality.objects.get(id=municipality_id)
            
            if action == 'approve':
                municipality_approval.approve(municipality, request.user)
                messages.success(request, f'{municipality.name} تایید شد و به اطلاعات جغرافیایی اضافه گردید. مدیر می‌تواند وارد پنل مدیریت شود.')

            elif action == 'reject':
                municipality.status = 'rejected'
                municipality.save()
                
                if municipality.admin_user:
                    municipality.admin_user.is_active = False
                    municipality.admin_user.save()
                
                messages.success(request, f'{municipality.name} رد شد.')
                
        except Municipality.DoesNotExist:
            messages.error(request, 'شهرداری/دهیاری یافت نشد.')
    
    return render(request, 'main/manage_municipalities.html', {'municipalities': municipalities})


@policy_required('admin.manage', api=True)
def admin_api_users_list(request):
    """API endpoint for admin to get users list with search, filter, pagination"""
    try:
        search = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', 'all')
        role_filter = request.GET.get('role', 'all')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        users = UserProfile.objects.filter(deleted_at__isnull=True)
        
        if search:
            users = users.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(national_id__icontains=search) |
                Q(mobile_number__icontains=search)
            )
        
        if status_filter != 'all':
            users = users.filter(approval_status=status_filter)
        
        if role_filter != 'all':
            users = users.filter(role=role_filter)
        
        users = users.order_by('-created_at')
        
        from django.core.paginator import Paginator
        paginator = Paginator(users, per_page)
        users_page = paginator.get_page(page)
        
        data = [{
            'id': user.id,
            'full_name': user.user.get_full_name(),
            'national_id': user.national_id or '-',
            'mobile': user.mobile_number or '-',
            'role': user.get_role_display(),
            'role_code': user.role,
            'status': user.get_approval_status_display(),
            'status_code': user.approval_status,
            'is_active': user.is_active,
            'created_at': user.created_at.strftime('%Y/%m/%d'),
        } for user in users_page]
        
        return JsonResponse({
            'success': True,
            'users': data,
            'pagination': {
                'current_page': users_page.number,
                'total_pages': paginator.num_pages,
                'total_items': paginator.count,
                'has_next': users_page.has_next(),
                'has_previous': users_page.has_previous(),
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_user_change_role(request, user_id):
    """API endpoint to change user role"""
    import json
    try:
        user_profile = get_object_or_404(UserProfile, id=user_id)
        data = json.loads(request.body)
        new_role = data.get('role')
        
        if new_role not in dict(UserProfile.USER_ROLES):
            return JsonResponse({
                'success': False,
                'message': 'نقش نامعتبر است'
            }, status=400)
        
        user_profile.role = new_role
        user_profile.save()
        if new_role == 'dehyari':
            municipality_approval.make_dehyari(user_profile)   # one dehyari per place, linked to its municipality

        Notification.objects.create(
            user=user_profile.user,
            notification_type='system',
            title='تغییر نقش کاربری',
            message=f'نقش کاربری شما به {user_profile.get_role_display()} تغییر کرد.'
        )
        
        return JsonResponse({
            'success': True,
            'message': 'نقش کاربر با موفقیت تغییر کرد',
            'new_role': user_profile.get_role_display()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_user_toggle_active(request, user_id):
    """API endpoint to activate/deactivate user"""
    try:
        user_profile = get_object_or_404(UserProfile, id=user_id)
        
        user_profile.is_active = not user_profile.is_active
        user_profile.user.is_active = user_profile.is_active
        user_profile.user.save()
        user_profile.save()
        
        status_text = 'فعال' if user_profile.is_active else 'غیرفعال'
        
        Notification.objects.create(
            user=user_profile.user,
            notification_type='system',
            title='تغییر وضعیت حساب',
            message=f'حساب کاربری شما {status_text} شد.'
        )
        
        return JsonResponse({
            'success': True,
            'message': f'کاربر با موفقیت {status_text} شد',
            'is_active': user_profile.is_active
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


INLINE_DECREE_TYPES = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}


@policy_required('admin.manage')
def municipality_decree(request, municipality_id):
    """Download a municipality's governor decree (admins only; the file is not under /media/)."""
    town = get_object_or_404(Municipality, pk=municipality_id)
    if not town.governor_decree:
        raise Http404
    name = os.path.basename(town.governor_decree.name)
    kind = INLINE_DECREE_TYPES.get(os.path.splitext(name)[1].lower())
    inline = request.GET.get('inline') == '1' and kind is not None      # only PDF/images are shown in the page
    response = FileResponse(town.governor_decree.open('rb'), as_attachment=not inline, filename=name,
                            content_type=kind if inline else None)
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@policy_required('admin.manage')
def municipality_decree_view(request, municipality_id):
    """In-site viewer for the governor decree: PDF/image inline, anything else as a download."""
    town = get_object_or_404(Municipality, pk=municipality_id)
    if not town.governor_decree:
        raise Http404
    kind = INLINE_DECREE_TYPES.get(os.path.splitext(town.governor_decree.name)[1].lower())
    return render(request, 'main/municipality_decree.html', {
        'town': town, 'is_pdf': kind == 'application/pdf', 'is_image': bool(kind and kind.startswith('image/'))})


@policy_required('admin.manage', api=True)
def admin_api_municipalities_list(request):
    """API endpoint to get municipalities list"""
    try:
        status_filter = request.GET.get('status', '')
        if status_filter and status_filter != 'all':
            municipalities = Municipality.objects.filter(status=status_filter).order_by('-created_at')
        else:
            municipalities = Municipality.objects.all().order_by('-created_at')

        data = [{
            'id': mun.id,
            'name': mun.name,
            'type': mun.get_municipality_type_display(),
            'province': mun.province or '',
            'county': mun.county or '',
            'district': mun.district or '',
            'city_village': mun.city_village or '',
            'contact_person': mun.manager_name or 'ثبت نشده',
            'contact_phone': mun.manager_phone or mun.official_phone or 'ثبت نشده',
            'contact_national_id': mun.manager_national_id or '',
            'population': mun.population or 0,
            'area_hectares': str(mun.area_hectares or 0),
            'status': mun.status,
            'status_display': mun.get_status_display(),
            'created_at': mun.created_at.strftime('%Y/%m/%d') if mun.created_at else '',
            'has_decree': bool(mun.governor_decree),
            'decree_url': reverse('main:municipality_decree_view', args=[mun.id]) if mun.governor_decree else '',
        } for mun in municipalities]

        return JsonResponse({
            'success': True,
            'municipalities': data,
            'count': len(data)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_municipality_action(request, municipality_id):
    """API endpoint to approve/reject municipality"""
    import json
    try:
        municipality = get_object_or_404(Municipality, id=municipality_id)
        action = None
        if request.body:
            try:
                data = json.loads(request.body)
                action = data.get('action')
            except Exception:
                pass
        if not action:
            action = request.POST.get('action')

        if action == 'approve':
            municipality_approval.approve(municipality, request.user)
            return JsonResponse({
                'success': True,
                'message': f'درخواست «{municipality.name}» با موفقیت تایید و فعال گردید.'
            })

        elif action == 'reject':
            municipality.status = 'rejected'
            municipality.save()

            if municipality.admin_user:
                municipality.admin_user.is_active = False
                municipality.admin_user.save()

                Notification.objects.create(
                    user=municipality.admin_user,
                    notification_type='request_status',
                    title='شهرداری/دهیاری رد شد',
                    message=f'درخواست ثبت شهرداری/دهیاری {municipality.name} رد شد.'
                )

            return JsonResponse({
                'success': True,
                'message': f'درخواست «{municipality.name}» رد شد.'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'عملیات نامعتبر است.'
            }, status=400)

            
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_services_list(request):
    """API endpoint to get services list"""
    try:
        services = Service.objects.all().order_by('category', 'name')
        
        data = [{
            'id': service.id,
            'name': service.name,
            'slug': service.slug,
            'category': service.get_category_display(),
            'icon': service.icon,
            'is_active': service.is_active,
            'required_role': service.get_required_role_display(),
            'estimated_duration': service.estimated_duration,
        } for service in services]
        
        return JsonResponse({
            'success': True,
            'services': data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_service_toggle_active(request, service_id):
    """API endpoint to toggle service active status"""
    try:
        service = get_object_or_404(Service, id=service_id)
        service.is_active = not service.is_active
        service.save()
        
        status_text = 'فعال' if service.is_active else 'غیرفعال'
        
        return JsonResponse({
            'success': True,
            'message': f'خدمت با موفقیت {status_text} شد',
            'is_active': service.is_active
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_service_create(request):
    """API endpoint to create a new service"""
    import json
    try:
        data = json.loads(request.body)
        
        service = Service.objects.create(
            name=data.get('name'),
            slug=data.get('slug'),
            description=data.get('description', ''),
            category=data.get('category'),
            icon=data.get('icon', '📋'),
            is_active=data.get('is_active', True),
            required_role=data.get('required_role', 'citizen'),
            estimated_duration=data.get('estimated_duration', ''),
            required_documents=data.get('required_documents', '')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'خدمت با موفقیت ایجاد شد',
            'service_id': service.id
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_service_update(request, service_id):
    """API endpoint to update a service"""
    import json
    try:
        service = get_object_or_404(Service, id=service_id)
        data = json.loads(request.body)
        
        service.name = data.get('name', service.name)
        service.description = data.get('description', service.description)
        service.category = data.get('category', service.category)
        service.icon = data.get('icon', service.icon)
        service.estimated_duration = data.get('estimated_duration', service.estimated_duration)
        service.required_documents = data.get('required_documents', service.required_documents)
        service.save()
        
        return JsonResponse({
            'success': True,
            'message': 'خدمت با موفقیت به‌روز شد'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_service_delete(request, service_id):
    """API endpoint to delete a service"""
    try:
        service = get_object_or_404(Service, id=service_id)
        service_name = service.name
        service.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'خدمت {service_name} با موفقیت حذف شد'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_reports_chart_data(request):
    """API endpoint to get chart data for reports"""
    from datetime import datetime, timedelta
    import json
    
    try:
        chart_type = request.GET.get('type', 'requests')
        
        if chart_type == 'requests':
            labels = []
            data = []
            for i in range(11, -1, -1):
                date = timezone.now() - timedelta(days=30*i)
                month_name = date.strftime('%B')[:3]
                count = ServiceRequest.objects.filter(
                    created_at__month=date.month,
                    created_at__year=date.year
                ).count()
                labels.append(month_name)
                data.append(count)
            
            return JsonResponse({
                'success': True,
                'labels': labels,
                'data': data,
                'label': 'درخواست‌های ماهانه'
            })
            
        elif chart_type == 'users':
            labels = []
            data = []
            for i in range(5, -1, -1):
                date = timezone.now() - timedelta(days=30*i)
                month_name = date.strftime('%B')[:3]
                count = UserProfile.objects.filter(
                    created_at__month=date.month,
                    created_at__year=date.year
                ).count()
                labels.append(month_name)
                data.append(count)
            
            return JsonResponse({
                'success': True,
                'labels': labels,
                'data': data,
                'label': 'کاربران جدید'
            })
            
        elif chart_type == 'status_distribution':
            labels = []
            data = []
            for status_code, status_name in ServiceRequest.STATUS_CHOICES:
                count = ServiceRequest.objects.filter(status=status_code).count()
                if count > 0:
                    labels.append(status_name)
                    data.append(count)
            
            return JsonResponse({
                'success': True,
                'labels': labels,
                'data': data,
                'label': 'توزیع وضعیت درخواست‌ها'
            })
        
        else:
            return JsonResponse({
                'success': False,
                'message': 'نوع نمودار نامعتبر'
            }, status=400)
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_reports_export_excel(request):
    """API endpoint to export reports to Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse
    import io
    
    try:
        report_type = request.GET.get('type', 'users')
        
        wb = Workbook()
        ws = wb.active
        ws.right_to_left = True
        
        if report_type == 'users':
            ws.title = 'گزارش کاربران'
            headers = ['ردیف', 'نام کامل', 'کد ملی', 'موبایل', 'نقش', 'وضعیت', 'تاریخ ثبت‌نام']
            users = UserProfile.objects.filter(deleted_at__isnull=True).order_by('-created_at')
            
            header_fill = PatternFill(start_color='0284c7', end_color='0284c7', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF', size=12)
            
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            for idx, user in enumerate(users, start=2):
                ws.cell(row=idx, column=1, value=idx-1)
                ws.cell(row=idx, column=2, value=user.user.get_full_name())
                ws.cell(row=idx, column=3, value=user.national_id or '-')
                ws.cell(row=idx, column=4, value=user.mobile_number or '-')
                ws.cell(row=idx, column=5, value=user.get_role_display())
                ws.cell(row=idx, column=6, value=user.get_approval_status_display())
                ws.cell(row=idx, column=7, value=user.created_at.strftime('%Y/%m/%d'))
        
        elif report_type == 'requests':
            ws.title = 'گزارش درخواست‌ها'
            headers = ['ردیف', 'عنوان', 'نوع درخواست', 'کاربر', 'وضعیت', 'تاریخ ثبت']
            requests = ServiceRequest.objects.all().order_by('-created_at')
            
            header_fill = PatternFill(start_color='0284c7', end_color='0284c7', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF', size=12)
            
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            for idx, req in enumerate(requests, start=2):
                ws.cell(row=idx, column=1, value=idx-1)
                ws.cell(row=idx, column=2, value=req.title)
                ws.cell(row=idx, column=3, value=req.get_request_type_display())
                ws.cell(row=idx, column=4, value=req.user.get_full_name())
                ws.cell(row=idx, column=5, value=req.get_status_display())
                ws.cell(row=idx, column=6, value=req.created_at.strftime('%Y/%m/%d'))
        
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename={report_type}_report.xlsx'
        return response
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_system_settings(request):
    """API endpoint to get system settings"""
    try:
        settings = {
            'maintenance_mode': False,
            'open_registration': True,
            'email_notifications': True,
            'sms_notifications': False,
            'auto_approve_users': False,
            'max_file_upload_size': 10,
            'session_timeout': 30,
        }
        
        return JsonResponse({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@policy_required('admin.manage', api=True)
def admin_api_update_system_settings(request):
    """API endpoint to update system settings"""
    import json
    try:
        data = json.loads(request.body)
        
        return JsonResponse({
            'success': True,
            'message': 'تنظیمات با موفقیت به‌روز شد'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
@role_required(['admin'])
def municipality_history(request, municipality_id):
    """تاریخچه و فعالیت‌های شهرداری/دهیاری"""
    municipality = get_object_or_404(Municipality, id=municipality_id)
    return render(request, 'main/admin/municipality_history.html', {'municipality': municipality})


@policy_required('admin.manage', api=True)
@login_required
def api_approve_property_ad(request, ad_id):
    """API to approve a property advertisement"""
    if not (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return JsonResponse({'success': False, 'message': 'دسترسی غیرمجاز است.'}, status=403)
    
    ad = get_object_or_404(PropertyAdvertisement, id=ad_id)
    admin_notes = request.POST.get('admin_notes', '') or 'آگهی توسط مدیر سیستم تایید شد.'
    ad.status = 'approved'
    ad.approved_at = timezone.now()
    ad.approved_by = request.user
    ad.admin_notes = admin_notes
    ad.save()

    Notification.objects.create(
        user=ad.user,
        notification_type='system_update',
        title='آگهی ملک شما تایید شد',
        message=f'آگهی ملک {ad.get_property_type_display()} شما در {ad.city_village or ad.county or "سیستم"} تایید و منتشر شد.'
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'message': 'آگهی با موفقیت تایید و منتشر شد.'})
    messages.success(request, 'آگهی با موفقیت تایید شد.')
    return redirect('main:admin_dashboard')


@policy_required('admin.manage', api=True)
@login_required
def api_reject_property_ad(request, ad_id):
    """API to reject a property advertisement"""
    if not (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return JsonResponse({'success': False, 'message': 'دسترسی غیرمجاز است.'}, status=403)

    ad = get_object_or_404(PropertyAdvertisement, id=ad_id)
    admin_notes = request.POST.get('admin_notes', '') or 'آگهی رد شد.'
    ad.status = 'rejected'
    ad.admin_notes = admin_notes
    ad.save()

    Notification.objects.create(
        user=ad.user,
        notification_type='system_update',
        title='آگهی ملک شما رد شد',
        message=f'آگهی ملک {ad.get_property_type_display()} شما رد شد. علت: {admin_notes}'
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'message': 'آگهی با موفقیت رد شد.'})
    messages.warning(request, 'آگهی رد شد.')
    return redirect('main:admin_dashboard')


@policy_required('admin.manage', api=True)
@login_required
def api_delete_property_ad(request, ad_id):
    """API to delete a property advertisement"""
    if not (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return JsonResponse({'success': False, 'message': 'دسترسی غیرمجاز است.'}, status=403)

    ad = get_object_or_404(PropertyAdvertisement, id=ad_id)
    ad.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'message': 'آگهی با موفقیت حذف گردید.'})
    messages.success(request, 'آگهی حذف شد.')
    return redirect('main:admin_dashboard')


@policy_required('admin.manage', api=True)
@login_required
def api_get_property_ad_detail(request, ad_id):
    """API to get full details and images of an ad for admin modal"""
    if not (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return JsonResponse({'success': False, 'message': 'دسترسی غیرمجاز است.'}, status=403)

    ad = get_object_or_404(PropertyAdvertisement, id=ad_id)
    
    images_data = []
    for img in ad.images.all():
        images_data.append({
            'id': img.id,
            'url': img.image.url if img.image else '',
            'caption': img.caption or '',
            'is_main': img.is_main
        })

    data = {
        'id': ad.id,
        'ad_type': ad.ad_type,
        'ad_type_display': ad.get_ad_type_display(),
        'property_type': ad.property_type,
        'property_type_display': ad.get_property_type_display(),
        'status': ad.status,
        'status_display': ad.get_status_display(),
        'total_area': float(ad.total_area) if ad.total_area else 0,
        'built_area': float(ad.built_area) if ad.built_area else 0,
        'floors': ad.floors,
        'bedrooms': ad.bedrooms,
        'parking': ad.parking,
        'construction_year': ad.construction_year,
        'province': ad.province or '',
        'county': ad.county or '',
        'district': ad.district or '',
        'city_village': ad.city_village or '',
        'is_village': ad.is_village,
        'dehestan': ad.dehestan or '',
        'address': ad.address or '',
        'sale_price': float(ad.sale_price) if ad.sale_price else None,
        'rent_price': float(ad.rent_price) if ad.rent_price else None,
        'deposit': float(ad.deposit) if ad.deposit else None,
        'price_negotiable': ad.price_negotiable,
        'description': ad.description or '',
        'contact_name': ad.contact_name or '',
        'contact_phone': ad.contact_phone or '',
        'admin_notes': ad.admin_notes or '',
        'created_at': ad.created_at.strftime('%Y/%m/%d %H:%M') if ad.created_at else '',
        'user_name': ad.user.get_full_name() or ad.user.username,
        'user_phone': getattr(ad.user.profile, 'mobile_number', ''),
        'images': images_data,
    }
    return JsonResponse({'success': True, 'data': data})


@policy_required('admin.manage', api=True)
@login_required
def api_approve_ad_edit(request, edit_id):
    """API to approve a property ad edit request"""
    if not (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return JsonResponse({'success': False, 'message': 'دسترسی غیرمجاز است.'}, status=403)

    edit_log = get_object_or_404(PropertyAdvertisementEditLog, id=edit_id)
    if edit_log.apply_changes():
        edit_log.status = 'approved'
        edit_log.reviewed_by = request.user
        edit_log.reviewed_at = timezone.now()
        edit_log.admin_notes = request.POST.get('admin_notes', '') or 'تغییرات توسط مدیر تایید شد.'
        edit_log.save()

        Notification.objects.create(
            user=edit_log.user,
            notification_type='system_update',
            title='درخواست ویرایش آگهی تایید شد',
            message=f'درخواست ویرایش آگهی {edit_log.advertisement.get_property_type_display()} شما تایید و اعمال شد.'
        )
        return JsonResponse({'success': True, 'message': 'درخواست ویرایش با موفقیت تایید و اعمال گردید.'})
    return JsonResponse({'success': False, 'message': 'خطا در اعمال تغییرات ویرایش.'}, status=400)


@policy_required('admin.manage', api=True)
@login_required
def api_reject_ad_edit(request, edit_id):
    """API to reject a property ad edit request"""
    if not (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return JsonResponse({'success': False, 'message': 'دسترسی غیرمجاز است.'}, status=403)

    edit_log = get_object_or_404(PropertyAdvertisementEditLog, id=edit_id)
    edit_log.status = 'rejected'
    edit_log.reviewed_by = request.user
    edit_log.reviewed_at = timezone.now()
    edit_log.admin_notes = request.POST.get('admin_notes', '') or 'درخواست ویرایش رد شد.'
    edit_log.save()

    Notification.objects.create(
        user=edit_log.user,
        notification_type='system_update',
        title='درخواست ویرایش آگهی رد شد',
        message=f'درخواست ویرایش آگهی {edit_log.advertisement.get_property_type_display()} شما رد شد.'
    )
    return JsonResponse({'success': True, 'message': 'درخواست ویرایش رد شد.'})


@policy_required('admin.manage', api=True)
@login_required
@require_http_methods(["POST"])
def api_toggle_user_access(request, user_id):
    """API endpoint to toggle user account access (block/unblock)"""
    if not (request.user.is_staff or request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'admin')):
        return JsonResponse({'success': False, 'message': 'شما دسترسی لازم برای این عملیات را ندارید.'}, status=403)

    try:
        user_target = User.objects.get(id=user_id)
        if user_target == request.user or user_target.is_superuser:
            return JsonResponse({'success': False, 'message': 'امکان تغییر وضعیت دسترسی مدیر سیستم یا کاربر جاری وجود ندارد.'}, status=400)

        profile = getattr(user_target, 'profile', None)
        current_status = bool(user_target.is_active and (profile.is_active if profile else True))
        new_status = not current_status

        user_target.is_active = new_status
        user_target.save()

        if profile:
            profile.is_active = new_status
            profile.save()

        from django.core.cache import cache
        user_name = user_target.get_full_name() or user_target.username
        if not new_status:
            cache.delete(f'user_last_seen_{user_target.id}')
            msg = f'دسترسی کاربر «{user_name}» به سامانه مسدود گردید.'
        else:
            msg = f'دسترسی کاربر «{user_name}» با موفقیت فعال و باز گردید.'

        return JsonResponse({
            'success': True,
            'is_active': new_status,
            'message': msg,
            'user_id': user_target.id,
            'user_name': user_name
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'کاربر مورد نظر یافت نشد.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'خطا: {str(e)}'}, status=500)


@policy_required('admin.manage', api=True)
@login_required
def api_users_monitoring_stats(request):
    """API endpoint to fetch live user monitoring statistics and statuses"""
    if not (request.user.is_staff or request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'admin')):
        return JsonResponse({'success': False, 'message': 'عدم دسترسی مجاز.'}, status=403)

    from django.core.cache import cache
    now = timezone.now()
    online_count = 0
    active_count = 0
    blocked_count = 0
    users_status_list = []

    profiles = UserProfile.objects.select_related('user').filter(deleted_at__isnull=True)
    for prof in profiles:
        u = prof.user
        last_seen = cache.get(f'user_last_seen_{u.id}')
        is_online = False
        if u.id == request.user.id or last_seen or (u.last_login and (now - u.last_login).total_seconds() < 300):
            is_online = True
            online_count += 1

        is_active = bool(u.is_active and prof.is_active)
        if is_active:
            active_count += 1
        else:
            blocked_count += 1

        users_status_list.append({
            'id': u.id,
            'is_online': is_online,
            'is_active': is_active
        })

    return JsonResponse({
        'success': True,
        'online_count': online_count,
        'active_count': active_count,
        'blocked_count': blocked_count,
        'total_count': len(users_status_list),
        'users': users_status_list
    })


@policy_required('admin.manage', api=True)
@login_required
@require_http_methods(["POST"])
def api_delete_user(request, user_id):
    """API endpoint to permanently delete a user account"""
    if not (request.user.is_staff or request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'admin')):
        return JsonResponse({'success': False, 'message': 'شما دسترسی لازم برای حذف کاربر را ندارید.'}, status=403)

    try:
        user_target = User.objects.get(id=user_id)
        if user_target == request.user:
            return JsonResponse({'success': False, 'message': 'شما نمی‌توانید حساب کاربری خودتان را حذف کنید.'}, status=400)

        if user_target.is_superuser:
            return JsonResponse({'success': False, 'message': 'امکان حذف کاربر با دسترسی مدیر ارشد (Superuser) وجود ندارد.'}, status=400)

        user_name = user_target.get_full_name() or user_target.username
        soft_delete_user(user_target)   # keeps the person's requests, payments and messages

        return JsonResponse({
            'success': True,
            'message': f'کاربر «{user_name}» با موفقیت از سیستم حذف گردید.',
            'user_id': user_id
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'کاربر مورد نظر یافت نشد.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'خطا در حذف کاربر: {str(e)}'}, status=500)

