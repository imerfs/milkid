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


@login_required
def my_requests(request):
    """User's service requests"""
    from main.views.citizen_panel import panel_tab_redirect
    if (moved := panel_tab_redirect(request, 'tracking')):
        return moved
    user_profile = request.user.profile
    
    # Get user's service requests
    service_requests = ServiceRequest.objects.filter(user=request.user).order_by('-created_at')

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(service_requests, 10)
    page_number = request.GET.get('page')
    requests_page = paginator.get_page(page_number)

    # Statistics
    stats = {
        'total': service_requests.count(),
        'pending': service_requests.filter(status='pending').count(),
        'approved': service_requests.filter(status='approved').count(),
        'rejected': service_requests.filter(status='rejected').count(),
        'completed': service_requests.filter(status='completed').count(),
    }

    context = {
        'user_profile': user_profile,
        'requests': requests_page,
        'stats': stats,
    }
    return render(request, 'main/my_requests.html', context)


@login_required
def create_request(request):
    """Create a new service request"""
    from main.views.citizen_panel import panel_tab_redirect
    if (moved := panel_tab_redirect(request, 'new-request')):
        return moved
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST, request.FILES)
        if form.is_valid():
            service_request = form.save(commit=False)
            service_request.user = request.user
            service_request.workflow_stage = 'expert_review'
            service_request.referral_target = 'engineer'
            prof = getattr(request.user, 'profile', None)
            if prof:
                if not service_request.province and prof.province:
                    service_request.province = Province.objects.filter(name=prof.province).first()
                if not service_request.county and prof.county:
                    service_request.county = County.objects.filter(name=prof.county).first()
                if not service_request.city_village and prof.city_village:
                    service_request.city_village = CityVillage.objects.filter(name=prof.city_village).first()
            service_request.save()
            service_request.add_workflow_step(
                action='ثبت درخواست توسط متقاضی - ارجاع اولیه به کارشناس دهیاری',
                from_user=request.user,
                to_role='engineer'
            )
            service_request.save()

            # Create notification
            Notification.objects.create(
                user=request.user,
                notification_type='request_submitted',
                title='درخواست ثبت شد',
                message=f'درخواست {service_request.title} با موفقیت ثبت شد.'
            )

            messages.success(request, 'درخواست شما با موفقیت ثبت شد.')
            return redirect('main:my_requests')
    else:
        form = ServiceRequestForm()

    context = {'form': form}
    return render(request, 'main/create_request.html', context)


@login_required
def request_detail(request, request_id):
    """View service request details"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    # Check if user has permission to view this request
    if request.user != service_request.user and not request.user.profile.is_staff_member():
        messages.error(request, 'شما اجازه مشاهده این درخواست را ندارید.')
        return redirect('main:dashboard')

    context = {
        'request': service_request,
    }
    return render(request, 'main/request_detail.html', context)


@policy_required('request.update_status')
def update_request_status(request, request_id):
    """Update service request status"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    try:
        lifecycle.set_status(service_request, request.user, request.POST.get('status'),
                             request.POST.get('admin_notes', ''))
        messages.success(request, 'وضعیت درخواست به‌روز شد.')
    except lifecycle.TransitionError as exc:
        messages.error(request, str(exc))
    return redirect('main:manage_requests')


def services_catalog(request):
    """View all available services"""
    services = Service.objects.filter(is_active=True).order_by('category', 'name')
    
    context = {
        'services': services,
    }
    return render(request, 'main/services_catalog.html', context)


def service_detail(request, slug):
    """View service details"""
    service = get_object_or_404(Service, slug=slug, is_active=True)
    
    context = {
        'service': service,
    }
    return render(request, 'main/service_detail.html', context)


def service_wizard(request, slug, step):
    """Service wizard for multi-step forms"""
    service = get_object_or_404(Service, slug=slug, is_active=True)
    service_step = get_object_or_404(ServiceStep, service=service, step_number=step)
    
    if request.method == 'POST':
        form = ServiceWizardStepForm(service_step, request.POST, request.FILES)
        if form.is_valid():
            # Store step data in session
            if 'service_wizard_data' not in request.session:
                request.session['service_wizard_data'] = {}
            
            request.session['service_wizard_data'][f'step_{step}'] = form.cleaned_data
            request.session.modified = True

            # Check if this is the last step
            next_step = ServiceStep.objects.filter(service=service, step_number=step + 1).first()
            if next_step:
                return redirect('main:service_wizard', slug=slug, step=step + 1)
            else:
                # Create service request from collected data
                # ... process wizard data ...
                messages.success(request, 'درخواست شما با موفقیت ثبت شد.')
                return redirect('main:my_requests')
    else:
        # Load data from session if available
        initial_data = request.session.get('service_wizard_data', {}).get(f'step_{step}', {})
        form = ServiceWizardStepForm(initial=initial_data, service_step=service_step)

    context = {
        'service': service,
        'step': service_step,
        'form': form,
        'current_step': step,
        'total_steps': service.steps.count(),
    }
    return render(request, f'main/services/{service.slug}/step{step}.html', context)


@login_required
def construction_permit_request(request):
    """Request construction permit"""
    if request.method == 'POST':
        form = ConstructionPermitForm(request.POST, request.FILES)
        if form.is_valid():
            prof = getattr(request.user, 'profile', None)
            prov_obj = Province.objects.filter(name=prof.province).first() if (prof and prof.province) else None
            county_obj = County.objects.filter(name=prof.county).first() if (prof and prof.county) else None
            village_obj = CityVillage.objects.filter(name=prof.city_village).first() if (prof and prof.city_village) else None

            service_request = ServiceRequest.objects.create(
                user=request.user,
                request_type='building_permit',
                title='درخواست صدور پروانه ساختمان',
                description=form.cleaned_data.get('description', ''),
                property_address=form.cleaned_data.get('property_address', ''),
                province=prov_obj,
                county=county_obj,
                city_village=village_obj,
                status='pending',
                workflow_stage='expert_review',
                referral_target='engineer'
            )
            service_request.add_workflow_step(
                action='ثبت درخواست پروانه ساختمان توسط متقاضی - ارجاع به کارشناس دهیاری',
                from_user=request.user,
                to_role='engineer'
            )
            service_request.save()

            messages.success(request, 'درخواست صدور پروانه ساختمان با موفقیت ثبت شد.')
            return redirect('main:my_requests')
    else:
        form = ConstructionPermitForm()

    context = {'form': form}
    return render(request, 'main/construction_permit.html', context)


def building_permit_form(request):
    """Building permit step 1"""
    return render(request, 'main/services/building-permits/step1.html')


def building_permit_step2(request):
    """Building permit step 2"""
    return render(request, 'main/services/building-permits/step2.html')


def building_permit_step3(request):
    """Building permit step 3"""
    return render(request, 'main/services/building-permits/step3.html')


def building_permit_step4(request):
    """Building permit step 4"""
    return render(request, 'main/services/building-permits/step4.html')


def building_permit_step5(request):
    """Building permit step 5"""
    return render(request, 'main/services/building-permits/step5.html')


def building_permit_step6(request):
    """Building permit step 6"""
    return render(request, 'main/services/building-permits/step6.html')


def building_permit_step7(request):
    """Building permit step 7"""
    return render(request, 'main/services/building-permits/step7.html')


def building_permit_step8(request):
    """Building permit step 8"""
    return render(request, 'main/services/building-permits/step8.html')


def building_permit_step9(request):
    """Building permit step 9"""
    return render(request, 'main/services/building-permits/step9.html')


def without_permit_form(request):
    """Construction without permit step 1"""
    return render(request, 'main/services/construction-without-permit/step1.html')


def without_permit_step2(request):
    """Construction without permit step 2"""
    return render(request, 'main/services/construction-without-permit/step2.html')


def without_permit_step3(request):
    """Construction without permit step 3"""
    return render(request, 'main/services/construction-without-permit/step3.html')


def without_permit_step4(request):
    """Construction without permit step 4"""
    return render(request, 'main/services/construction-without-permit/step4.html')


def without_permit_step5(request):
    """Construction without permit step 5"""
    return render(request, 'main/services/construction-without-permit/step5.html')


def without_permit_step6(request):
    """Construction without permit step 6"""
    return render(request, 'main/services/construction-without-permit/step6.html')


def property_deed_form(request):
    """Property deed step 1"""
    return render(request, 'main/services/property-deed/step1.html')


def property_deed_step2(request):
    """Property deed step 2"""
    return render(request, 'main/services/property-deed/step2.html')


def property_deed_step3(request):
    """Property deed step 3"""
    return render(request, 'main/services/property-deed/step3.html')


def property_deed_step4(request):
    """Property deed step 4"""
    return render(request, 'main/services/property-deed/step4.html')


def land_use_change_form(request):
    """Land use change step 1"""
    return render(request, 'main/services/land-use-change/step1.html')


def land_use_change_step2(request):
    """Land use change step 2"""
    return render(request, 'main/services/land-use-change/step2.html')


def land_use_change_step3(request):
    """Land use change step 3"""
    return render(request, 'main/services/land-use-change/step3.html')


def hadi_plan_form(request):
    """Hadi plan step 1"""
    return render(request, 'main/services/join-development-plan/step1.html')


def hadi_plan_step2(request):
    """Hadi plan step 2"""
    return render(request, 'main/services/join-development-plan/step2.html')


def hadi_plan_step3(request):
    """Hadi plan step 3"""
    return render(request, 'main/services/join-development-plan/step3.html')


def residence_confirmation_form(request):
    """Residence confirmation step 1"""
    return render(request, 'main/services/residence-confirmation/step1.html')


def residence_confirmation_step2(request):
    """Residence confirmation step 2"""
    return render(request, 'main/services/residence-confirmation/step2.html')


def residence_confirmation_step3(request):
    """Residence confirmation step 3"""
    return render(request, 'main/services/residence-confirmation/step3.html')
