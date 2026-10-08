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


@policy_required('council.view')
def council_dashboard(request):
    """Dashboard for council members (شورا)"""
    from main.models import Vote, CouncilComment
    
    user_profile = request.user.profile
    
    municipality_filter = Q()
    if user_profile.city_village:
        municipality_filter = Q(user__profile__city_village=user_profile.city_village)
    
    voting_requests = ServiceRequest.objects.filter(
        municipality_filter,
        status__in=['pending', 'in_review']
    ).exclude(
        votes__council_member=request.user
    ).order_by('-created_at')[:10]
    
    financial_requests = Payment.objects.filter(
        municipality_filter,
        status='pending'
    ).select_related('user', 'property').order_by('-created_at')[:10]
    
    deed_requests = ServiceRequest.objects.filter(
        municipality_filter,
        request_type='property_deed',
        status__in=['pending', 'in_review']
    ).order_by('-created_at')[:10]
    
    recent_votes = Vote.objects.filter(
        council_member=request.user
    ).select_related('request').order_by('-voted_at')[:5]
    
    notifications = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).order_by('-created_at')[:5]
    
    stats = {
        'pending_votes': voting_requests.count(),
        'total_votes_cast': Vote.objects.filter(council_member=request.user).count(),
        'pending_financial': financial_requests.count(),
        'pending_deeds': deed_requests.count(),
        'unread_notifications': notifications.count(),
        'total_requests': ServiceRequest.objects.filter(municipality_filter).count(),
        'approved_this_month': ServiceRequest.objects.filter(
            municipality_filter,
            status='approved',
            updated_at__month=timezone.now().month
        ).count(),
        'meetings_held': 24,
    }
    
    context = {
        'user_profile': user_profile,
        'voting_requests': voting_requests,
        'financial_requests': financial_requests,
        'deed_requests': deed_requests,
        'recent_votes': recent_votes,
        'notifications': notifications,
        'stats': stats,
    }
    return render(request, 'main/dashboards/council.html', context)


@policy_required('council.view')
def council_voting_list(request):
    """List of requests requiring council vote"""
    from main.models import Vote
    
    user_profile = request.user.profile
    
    municipality_filter = Q()
    if user_profile.city_village:
        municipality_filter = Q(user__profile__city_village=user_profile.city_village)
    
    requests_list = ServiceRequest.objects.filter(
        municipality_filter,
        status__in=['pending', 'in_review']
    ).exclude(
        votes__council_member=request.user
    ).select_related('user', 'service').prefetch_related('votes').order_by('-created_at')
    
    paginator = Paginator(requests_list, 10)
    page_number = request.GET.get('page')
    requests = paginator.get_page(page_number)
    
    context = {
        'user_profile': user_profile,
        'requests': requests,
    }
    return render(request, 'main/dashboards/council.html', context)


@policy_required('council.vote')
def council_submit_vote(request, request_id):
    """Submit a vote on a request"""
    from main.models import Vote
    
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    if request.method == 'POST':
        vote_choice = request.POST.get('vote')
        reason = request.POST.get('reason', '')
        
        if vote_choice in ['approve', 'reject', 'abstain']:
            Vote.objects.update_or_create(
                request=service_request,
                council_member=request.user,
                defaults={
                    'vote': vote_choice,
                    'reason': reason
                }
            )
            
            # Log in workflow history
            vote_names = {'approve': 'موافق', 'reject': 'مخالف', 'abstain': 'ممتنع'}
            service_request.add_workflow_step(
                action=f'ثبت رای {vote_names.get(vote_choice, vote_choice)} توسط عضو شورا ({request.user.get_full_name() or request.user.username})',
                from_user=request.user,
                to_role='engineer',
                notes=reason
            )
            service_request.save()

            Notification.objects.create(
                user=service_request.user,
                notification_type='request_status',
                title='رای شورا ثبت شد',
                message=f'عضو شورا نسبت به درخواست "{service_request.title}" رای خود را ثبت کرد.',
                related_request=service_request
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'رای شما با موفقیت ثبت شد.'})

            messages.success(request, 'رای شما با موفقیت ثبت شد.')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'نوع رای نامعتبر است.'}, status=400)
            messages.error(request, 'نوع رای نامعتبر است.')
    
    return redirect('main:council_dashboard')


@policy_required('council.view')
def council_review_requests(request):
    """Review all requests with filtering and pagination"""
    from main.models import Vote, CouncilComment
    
    user_profile = request.user.profile
    
    municipality_filter = Q()
    if user_profile.city_village:
        municipality_filter = Q(user__profile__city_village=user_profile.city_village)
    
    requests_list = ServiceRequest.objects.filter(municipality_filter)
    
    status_filter = request.GET.get('status')
    if status_filter:
        requests_list = requests_list.filter(status=status_filter)
    
    request_type_filter = request.GET.get('request_type')
    if request_type_filter:
        requests_list = requests_list.filter(request_type=request_type_filter)
    
    search_query = request.GET.get('search')
    if search_query:
        requests_list = requests_list.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    requests_list = requests_list.select_related('user', 'service').prefetch_related(
        'votes', 'council_comments'
    ).order_by('-created_at')
    
    paginator = Paginator(requests_list, 15)
    page_number = request.GET.get('page')
    requests = paginator.get_page(page_number)
    
    context = {
        'user_profile': user_profile,
        'requests': requests,
        'status_filter': status_filter,
        'request_type_filter': request_type_filter,
        'search_query': search_query,
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'request_types': ServiceRequest.REQUEST_TYPES,
    }
    return render(request, 'main/dashboards/council_review.html', context)


@policy_required('council.view')
def council_request_detail(request, request_id):
    """Detailed view of a request with voting and commenting"""
    from main.models import Vote, CouncilComment
    
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related('user', 'service', 'assigned_to').prefetch_related(
            'votes__council_member__profile',
            'council_comments__council_member__profile',
            'documents'
        ),
        id=request_id
    )
    
    user_vote = Vote.objects.filter(
        request=service_request,
        council_member=request.user
    ).first()
    
    vote_summary = {
        'approve': Vote.objects.filter(request=service_request, vote='approve').count(),
        'reject': Vote.objects.filter(request=service_request, vote='reject').count(),
        'abstain': Vote.objects.filter(request=service_request, vote='abstain').count(),
    }
    
    context = {
        'user_profile': request.user.profile,
        'service_request': service_request,
        'user_vote': user_vote,
        'vote_summary': vote_summary,
    }
    return render(request, 'main/dashboards/council_request_detail.html', context)


@policy_required('council.view')
def council_add_comment(request, request_id):
    """Add a comment to a request"""
    from main.models import CouncilComment
    
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    if request.method == 'POST':
        comment_text = request.POST.get('comment')
        
        if comment_text:
            CouncilComment.objects.create(
                request=service_request,
                council_member=request.user,
                comment=comment_text
            )
            
            Notification.objects.create(
                user=service_request.user,
                notification_type='request_status',
                title='نظر جدید شورا',
                message=f'شورا نظر جدیدی در مورد درخواست "{service_request.title}" ثبت کرد.',
                related_request=service_request
            )
            
            messages.success(request, 'نظر شما با موفقیت ثبت شد.')
        else:
            messages.error(request, 'لطفا متن نظر را وارد کنید.')
    
    return redirect('main:council_request_detail', request_id=request_id)


@policy_required('council.view')
def council_financial_reports(request):
    """Financial reports and payment approvals for council"""
    user_profile = request.user.profile
    
    municipality_filter = Q()
    if user_profile.city_village:
        municipality_filter = Q(user__profile__city_village=user_profile.city_village)
    
    pending_payments = Payment.objects.filter(
        municipality_filter,
        status='pending'
    ).select_related('user', 'property').order_by('-created_at')
    
    paid_payments = Payment.objects.filter(
        municipality_filter,
        status='paid',
        paid_date__month=timezone.now().month
    ).select_related('user', 'property').order_by('-paid_date')
    
    financial_stats = {
        'total_pending': pending_payments.aggregate(Sum('amount'))['amount__sum'] or 0,
        'total_received_month': paid_payments.aggregate(Sum('amount'))['amount__sum'] or 0,
        'pending_count': pending_payments.count(),
        'paid_count': paid_payments.count(),
    }
    
    paginator = Paginator(pending_payments, 15)
    page_number = request.GET.get('page')
    payments = paginator.get_page(page_number)
    
    context = {
        'user_profile': user_profile,
        'payments': payments,
        'paid_payments': paid_payments[:10],
        'financial_stats': financial_stats,
    }
    return render(request, 'main/dashboards/council_financial.html', context)
