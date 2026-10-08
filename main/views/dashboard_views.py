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


def home(request):
    """Homepage with services menu and announcements"""
    # Get featured services from database safely
    services = []
    try:
        featured_services = Service.objects.filter(is_active=True)[:6]
        for service in featured_services:
            services.append({
                'name': service.name, 
                'icon': service.icon, 
                'url': f'/services/{service.slug}/'
            })
    except:
        # Database not ready yet
        pass

    # Fallback to static services if no database services
    if not services:
        services = [
            {'name': 'صدور پروانه ساختمان', 'icon': '🏗️', 'url': '/services/'},
            {'name': 'بدون پروانه', 'icon': '📋', 'url': '/services/'},
            {'name': 'تایید سکونت', 'icon': '🏠', 'url': '/services/'},
            {'name': 'خدمات شهرداری', 'icon': '🏛️', 'url': '/services/'},
            {'name': 'املاک و مستغلات', 'icon': '🏘️', 'url': '/services/'},
            {'name': 'پشتیبانی', 'icon': '💬', 'url': '/services/'},
        ]

    announcements = [
        {'title': 'اطلاعیه مهم درباره صدور پروانه ساختمان', 'date': '1403/01/15'},
        {'title': 'تغییرات جدید در قوانین شهرسازی', 'date': '1403/01/10'},
        {'title': 'راه‌اندازی سامانه جدید خدمات الکترونیک', 'date': '1403/01/05'},
    ]

    properties = [
        {'title': 'زمین 500 متری در مرکز شهر', 'price': '2,500,000,000', 'location': 'مرکز شهر'},
        {'title': 'خانه ویلایی 200 متری', 'price': '3,200,000,000', 'location': 'حومه شهر'},
        {'title': 'آپارتمان 120 متری', 'price': '1,800,000,000', 'location': 'منطقه 2'},
    ]

    context = {
        'services': services,
        'announcements': announcements,
        'properties': properties,
    }
    return render(request, 'main/home.html', context)


@login_required
def dashboard(request):
    """
    Role-based dashboard redirect
    """
    try:
        user_profile = request.user.profile

        if not user_profile.is_verified and user_profile.role != 'admin':
            messages.warning(request, 'حساب کاربری شما در انتظار تایید مدیر سیستم است.')
            return render(request, 'main/pending_verification.html')

        # Redirect based on user role to specific dashboards
        role_redirects = {
            'admin': 'main:admin_dashboard',        # مدیر سیستم
            'dehyari': 'main:dehyari_dashboard',    # دهیار/شهردار  
            'council': 'main:council_dashboard',    # شورا
            'engineer': 'main:dehyari_expert_dashboard',  # کارشناس دهیاری
            'inspector': 'main:inspector_dashboard', # ناظر فنی
            'accountant': 'main:accountant_dashboard', # مسئول مالی
            'citizen': 'main:owner_dashboard',      # شهروند
            'owner': 'main:owner_dashboard',        # مالک
        }

        redirect_url = role_redirects.get(user_profile.role)
        if redirect_url:
            return redirect(redirect_url)
        else:
            # Default fallback to owner dashboard for any other roles
            return redirect('main:owner_dashboard')

    except UserProfile.DoesNotExist:
        messages.error(request, 'پروفایل کاربری یافت نشد.')
        return redirect('main:home')


def user_dashboard(request):
    """Enhanced dashboard for regular residents/owners"""
    user_profile = request.user.profile

    service_requests = ServiceRequest.objects.filter(user=request.user).order_by('-created_at')[:5]
    unread_notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]
    active_requests = ServiceRequest.objects.filter(user=request.user).exclude(status__in=['completed', 'rejected']).count()
    unpaid_payments = Payment.objects.filter(user=request.user, status='pending').count()
    all_services = Service.objects.filter(is_active=True)
    user_documents = RequestDocument.objects.filter(request__user=request.user).order_by('-uploaded_at')[:5]

    stats = {
        'total_requests': ServiceRequest.objects.filter(user=request.user).count(),
        'active_requests': active_requests,
        'pending_requests': ServiceRequest.objects.filter(user=request.user, status='pending').count(),
        'approved_requests': ServiceRequest.objects.filter(user=request.user, status='approved').count(),
        'completed_requests': ServiceRequest.objects.filter(user=request.user, status='completed').count(),
        'rejected_requests': ServiceRequest.objects.filter(user=request.user, status='rejected').count(),
        'unpaid_payments': unpaid_payments,
        'unread_notifications': unread_notifications.count(),
        'total_documents': RequestDocument.objects.filter(request__user=request.user).count(),
    }

    context = {
        'user_profile': user_profile,
        'service_requests': service_requests,
        'unread_notifications': unread_notifications,
        'user_documents': user_documents,
        'all_services': all_services,
        'stats': stats,
    }
    return render(request, 'main/dashboards/user_dashboard.html', context)


def dashboard_submit_request(request):
    """Submit a new service request from dashboard"""
    from django.http import HttpResponse
    
    if request.method == 'POST':
        service_id = request.POST.get('service')
        title = request.POST.get('title')
        description = request.POST.get('description')
        property_address = request.POST.get('property_address', '')
        
        if not service_id or not title or not description:
            messages.error(request, 'لطفا تمامی فیلدهای ضروری را پر کنید.')
            return redirect('main:user_dashboard')
        
        try:
            service = Service.objects.get(id=service_id)
            
            if not service.is_active:
                messages.error(request, 'این خدمت در حال حاضر غیرفعال است و امکان ثبت درخواست وجود ندارد.')
                return redirect('main:user_dashboard')
            
            prof = getattr(request.user, 'profile', None)
            prov_obj = Province.objects.filter(name=prof.province).first() if (prof and prof.province) else None
            county_obj = County.objects.filter(name=prof.county).first() if (prof and prof.county) else None
            village_obj = CityVillage.objects.filter(name=prof.city_village).first() if (prof and prof.city_village) else None
            if not village_obj and prof and prof.city_village_name:
                village_obj = CityVillage.objects.filter(name=prof.city_village_name).first()

            service_request = ServiceRequest.objects.create(
                user=request.user,
                service=service,
                request_type='other',
                title=title,
                description=description,
                property_address=property_address,
                province=prov_obj,
                county=county_obj,
                city_village=village_obj,
                status='pending',
                workflow_stage='expert_review',
                referral_target='engineer'
            )
            service_request.add_workflow_step(
                action='ثبت اولیه توسط متقاضی - ارجاع به کارشناس دهیاری',
                from_user=request.user,
                to_role='engineer'
            )
            service_request.save()
            
            if request.FILES:
                for file_key in request.FILES:
                    uploaded_file = request.FILES[file_key]
                    RequestDocument.objects.create(
                        request=service_request,
                        document=uploaded_file,
                        document_name=uploaded_file.name
                    )
            
            Notification.objects.create(
                user=request.user,
                notification_type='request_status',
                title='درخواست جدید ثبت شد',
                message=f'درخواست {title} با موفقیت ثبت شد و در حال بررسی است.'
            )
            
            messages.success(request, 'درخواست شما با موفقیت ثبت شد.')
            return redirect('main:user_dashboard')
            
        except Service.DoesNotExist:
            messages.error(request, 'خدمت انتخابی یافت نشد.')
            return redirect('main:user_dashboard')
    
    return redirect('main:user_dashboard')


def dashboard_track_requests(request):
    """Track all user requests with pagination and filtering"""
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    requests_list = ServiceRequest.objects.filter(user=request.user).order_by('-created_at')
    
    if status_filter:
        requests_list = requests_list.filter(status=status_filter)
    
    if search_query:
        requests_list = requests_list.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query) |
            Q(parcel_number__icontains=search_query)
        )
    
    paginator = Paginator(requests_list, 10)
    page_number = request.GET.get('page')
    requests_page = paginator.get_page(page_number)
    
    context = {
        'requests': requests_page,
        'status_filter': status_filter,
        'search_query': search_query,
        'user_profile': request.user.profile,
    }
    
    return render(request, 'main/dashboards/track_requests.html', context)


def dashboard_request_detail(request, request_id):
    """View detailed information about a specific request"""
    service_request = get_object_or_404(ServiceRequest, id=request_id, user=request.user)
    documents = service_request.documents.all()
    
    context = {
        'service_request': service_request,
        'documents': documents,
        'user_profile': request.user.profile,
    }
    
    return render(request, 'main/dashboards/request_detail.html', context)


def dashboard_upload_document(request):
    """Upload a document to a service request"""
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        document_name = request.POST.get('document_name')
        
        if 'document' not in request.FILES:
            messages.error(request, 'لطفا فایل را انتخاب کنید.')
            return redirect('main:user_dashboard')
        
        try:
            service_request = ServiceRequest.objects.get(id=request_id, user=request.user)
            
            RequestDocument.objects.create(
                request=service_request,
                document=request.FILES['document'],
                document_name=document_name or request.FILES['document'].name
            )
            
            messages.success(request, 'مدرک با موفقیت آپلود شد.')
        except ServiceRequest.DoesNotExist:
            messages.error(request, 'درخواست یافت نشد.')
    
    return redirect('main:user_dashboard')


def dashboard_delete_document(request, document_id):
    """Delete a document from user's requests"""
    document = get_object_or_404(RequestDocument, id=document_id, request__user=request.user)
    
    if request.method == 'POST':
        document_name = document.document_name
        document.document.delete()
        document.delete()
        messages.success(request, f'مدرک "{document_name}" با موفقیت حذف شد.')
    
    return redirect(request.META.get('HTTP_REFERER', 'main:user_dashboard'))


def dashboard_download_document(request, document_id):
    """Download a document with proper role-based access control"""
    document = get_object_or_404(RequestDocument, id=document_id)
    
    # Permission check: Owner of request OR staff member (dehyari, council, engineer, inspector, admin)
    user_role = getattr(request.user.profile, 'role', 'citizen')
    is_owner = (document.request.user == request.user)
    is_staff = (user_role in ['dehyari', 'council', 'engineer', 'inspector', 'admin'])
    
    if not (is_owner or is_staff):
        return HttpResponseForbidden("شما دسترسی لازم برای دریافت این مدرک را ندارید.")
    
    if document.document:
        try:
            response = FileResponse(document.document.open('rb'))
            response['Content-Disposition'] = f'attachment; filename="{document.document_name}"'
            return response
        except Exception:
            raise Http404("فایل یافت نشد")
    
    raise Http404("فایل یافت نشد")


def dashboard_payments(request):
    """View all user payments"""
    status_filter = request.GET.get('status', '')
    
    payments_list = Payment.objects.filter(user=request.user).order_by('-created_at')
    
    if status_filter:
        payments_list = payments_list.filter(status=status_filter)
    
    paginator = Paginator(payments_list, 10)
    page_number = request.GET.get('page')
    payments_page = paginator.get_page(page_number)
    
    total_pending = Payment.objects.filter(user=request.user, status='pending').aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    context = {
        'payments': payments_page,
        'status_filter': status_filter,
        'total_pending': total_pending,
        'user_profile': request.user.profile,
    }
    
    return render(request, 'main/dashboards/payments.html', context)


def dashboard_messages(request):
    """View all user notifications and messages"""
    notifications_list = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    paginator = Paginator(notifications_list, 15)
    page_number = request.GET.get('page')
    notifications_page = paginator.get_page(page_number)
    
    notifications_list.filter(is_read=False).update(is_read=True)
    
    context = {
        'notifications': notifications_page,
        'user_profile': request.user.profile,
    }
    
    return render(request, 'main/dashboards/messages.html', context)


def notifications(request):
    """View user notifications"""
    user_notifications = Notification.objects.filter(user=request.user).order_by('-created_at')

    # Mark as read
    if request.method == 'POST':
        notification_id = request.POST.get('notification_id')
        try:
            notification = Notification.objects.get(id=notification_id, user=request.user)
            notification.is_read = True
            notification.save()
        except Notification.DoesNotExist:
            pass

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(user_notifications, 20)
    page_number = request.GET.get('page')
    notifications_page = paginator.get_page(page_number)

    context = {
        'notifications': notifications_page,
    }
    return render(request, 'main/notifications.html', context)


def analytics_dashboard(request):
    """Comprehensive analytics dashboard for municipalities"""
    municipality = None
    if hasattr(request.user, 'managed_municipality'):
        municipality = request.user.managed_municipality
    
    stats = {
        'total_requests': ServiceRequest.objects.count(),
        'pending_requests': ServiceRequest.objects.filter(status='pending').count(),
        'approved_requests': ServiceRequest.objects.filter(status='approved').count(),
        'total_properties': Property.objects.count(),
        'properties_for_sale': Property.objects.filter(is_for_sale=True).count(),
        'total_users': User.objects.count(),
        'verified_users': UserProfile.objects.filter(is_verified=True).count(),
    }
    
    from django.db.models import Count
    from datetime import datetime, timedelta
    
    request_trends = []
    for i in range(12):
        date = timezone.now() - timedelta(days=30*i)
        count = ServiceRequest.objects.filter(
            created_at__month=date.month,
            created_at__year=date.year
        ).count()
        request_trends.append({
            'month': date.strftime('%Y-%m'),
            'count': count
        })
    
    context = {
        'municipality': municipality,
        'stats': stats,
        'request_trends': request_trends,
    }
    return render(request, 'main/analytics_dashboard.html', context)
