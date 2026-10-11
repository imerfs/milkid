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
from main.models import (PropertyImage, UserProfile, ServiceRequest, Notification, RequestDocument, Service, ServiceStep, Property, Municipality,
                   PropertyAdvertisement, AutoCADFile, PropertyData, Payment, Conversation, Message, MessageRecipient,
                   ViolationReport, Inspection, InspectionDocument, TechnicalReport, Province, County, District, CityVillage,
                   Vote, CouncilComment, PropertyAdvertisementEditLog)


@login_required
def owner_dashboard(request):
    """Dashboard for property owners and residents"""
    user_profile = request.user.profile
    
    # Get user's properties
    user_properties = Property.objects.filter(owner_national_id=user_profile.national_id)[:5]
    
    # Get user's service requests
    service_requests = ServiceRequest.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    # Get user's property advertisements
    property_ads = PropertyAdvertisement.objects.filter(user=request.user).order_by('-created_at')[:3]
    
    # Get unread notifications
    unread_notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]
    
    # Statistics
    stats = {
        'total_properties': user_properties.count(),
        'total_requests': service_requests.count(),
        'pending_requests': ServiceRequest.objects.filter(user=request.user, status='pending').count(),
        'approved_requests': ServiceRequest.objects.filter(user=request.user, status='approved').count(),
        'total_ads': property_ads.count(),
        'unread_notifications': unread_notifications.count(),
    }
    
    context = {
        'user_profile': user_profile,
        'user_properties': user_properties,
        'service_requests': service_requests,
        'property_ads': property_ads,
        'unread_notifications': unread_notifications,
        'stats': stats,
    }
    return render(request, 'main/dashboards/Owner.html', context)


def property_marketplace(request):
    """Property marketplace for buying/selling"""
    properties = Property.objects.filter(
        Q(is_for_sale=True) | Q(is_for_rent=True),
        status='active'
    ).order_by('-created_at')

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(properties, 12)
    page_number = request.GET.get('page')
    properties_page = paginator.get_page(page_number)

    context = {
        'properties': properties_page,
    }
    return render(request, 'main/property_marketplace.html', context)


def property_listings(request):
    """Property listings view supporting PropertyAdvertisement"""
    ads = PropertyAdvertisement.objects.filter(status='approved').order_by('-created_at')

    # Allow staff/admin to view other statuses if specified
    status_filter = request.GET.get('status')
    if status_filter and request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        if status_filter == 'all':
            ads = PropertyAdvertisement.objects.all().order_by('-created_at')
        else:
            ads = PropertyAdvertisement.objects.filter(status=status_filter).order_by('-created_at')

    # Search query
    search_query = request.GET.get('search') or request.GET.get('q', '')
    if search_query:
        search_query = search_query.strip()
        ads = ads.filter(
            Q(address__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(city_village__icontains=search_query) |
            Q(county__icontains=search_query) |
            Q(province__icontains=search_query) |
            Q(contact_name__icontains=search_query)
        )

    # Geographic filters
    province = (request.GET.get('province') or '').strip()
    county = (request.GET.get('county') or '').strip()
    district = (request.GET.get('district') or '').strip()
    city_village = (request.GET.get('city_village') or '').strip()

    if province:
        if province.isdigit():
            p_obj = Province.objects.filter(id=int(province)).first()
            if p_obj:
                ads = ads.filter(province__icontains=p_obj.name)
        else:
            ads = ads.filter(province__icontains=province)

    if county:
        if county.isdigit():
            c_obj = County.objects.filter(id=int(county)).first()
            if c_obj:
                ads = ads.filter(county__icontains=c_obj.name)
        else:
            ads = ads.filter(county__icontains=county)

    if district:
        if district.isdigit():
            d_obj = District.objects.filter(id=int(district)).first()
            if d_obj:
                ads = ads.filter(district__icontains=d_obj.name)
        else:
            ads = ads.filter(district__icontains=district)

    if city_village:
        if city_village.isdigit():
            cv_obj = CityVillage.objects.filter(id=int(city_village)).first()
            if cv_obj:
                ads = ads.filter(city_village__icontains=cv_obj.name)
        else:
            ads = ads.filter(city_village__icontains=city_village)

    # Ad type & Property type filters
    ad_type = (request.GET.get('ad_type') or '').strip()
    if ad_type and ad_type in ['sale', 'rent', 'both']:
        ads = ads.filter(ad_type=ad_type)

    property_type = (request.GET.get('property_type') or '').strip()
    if property_type:
        ads = ads.filter(property_type=property_type)

    # Price range
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        try:
            val = float(min_price)
            ads = ads.filter(Q(sale_price__gte=val) | Q(rent_price__gte=val) | Q(deposit__gte=val))
        except (ValueError, TypeError):
            pass

    if max_price:
        try:
            val = float(max_price)
            ads = ads.filter(Q(sale_price__lte=val) | Q(rent_price__lte=val) | Q(deposit__lte=val))
        except (ValueError, TypeError):
            pass

    # Area range
    min_area = request.GET.get('min_area')
    max_area = request.GET.get('max_area')
    if min_area:
        try:
            val = float(min_area)
            ads = ads.filter(total_area__gte=val)
        except (ValueError, TypeError):
            pass

    if max_area:
        try:
            val = float(max_area)
            ads = ads.filter(total_area__lte=val)
        except (ValueError, TypeError):
            pass

    total_count = ads.count()

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(ads, 12)
    page_number = request.GET.get('page')
    ads_page = paginator.get_page(page_number)

    current_filters = {
        'search': search_query,
        'province': province,
        'county': county,
        'district': district,
        'city_village': city_village,
        'ad_type': ad_type,
        'property_type': property_type,
        'min_price': min_price or '',
        'max_price': max_price or '',
        'min_area': min_area or '',
        'max_area': max_area or '',
    }

    context = {
        'ads': ads_page,
        'properties': ads_page,
        'total_count': total_count,
        'current_filters': current_filters,
        'search_query': search_query,
    }
    return render(request, 'main/property_listings.html', context)


def _may_see_unapproved(user, ad):
    """Only the owner and administrators may read an advertisement that is not approved."""
    if not user.is_authenticated:
        return False
    if user == ad.user or user.is_staff or user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role == 'admin')


def property_detail(request, property_id):
    """View property details (supports PropertyAdvertisement and legacy Property)"""
    ad = PropertyAdvertisement.objects.filter(id=property_id).first()
    if ad:
        if ad.status != 'approved' and not _may_see_unapproved(request.user, ad):
            raise Http404
        context = {
            'property': ad,
            'ad': ad,
            'images': ad.images.all(),
        }
        return render(request, 'main/property_detail.html', context)

    property_obj = get_object_or_404(Property, id=property_id)
    context = {
        'property': property_obj,
    }
    return render(request, 'main/property_detail.html', context)


@login_required
def register_property(request):
    """Register new property"""
    if request.method == 'POST':
        form = PropertyRegistrationForm(request.POST)
        if form.is_valid():
            property_obj = form.save(commit=False)
            property_obj.created_by = request.user
            property_obj.save()

            messages.success(request, 'ملک با موفقیت ثبت شد.')
            return redirect('main:property_listings')
    else:
        form = PropertyRegistrationForm()

    context = {'form': form}
    return render(request, 'main/register_property.html', context)


@login_required
def property_advertisement_form(request):
    """Property advertisement submission"""
    if request.method == 'POST':
        form = PropertyAdvertisementForm(request.POST, request.FILES)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.user = request.user
            ad.status = 'pending'

            # Resolve numeric IDs to actual names for geographical fields
            province_val = form.cleaned_data.get('province') or request.POST.get('province')
            county_val = form.cleaned_data.get('county') or request.POST.get('county')
            district_val = form.cleaned_data.get('district') or request.POST.get('district')
            city_village_val = form.cleaned_data.get('city_village') or request.POST.get('city_village')

            if province_val and str(province_val).isdigit():
                p = Province.objects.filter(id=int(province_val)).first()
                if p:
                    ad.province = p.name
            elif province_val:
                ad.province = str(province_val).strip()

            if county_val and str(county_val).isdigit():
                c = County.objects.filter(id=int(county_val)).first()
                if c:
                    ad.county = c.name
            elif county_val:
                ad.county = str(county_val).strip()

            if district_val and str(district_val).isdigit():
                d = District.objects.filter(id=int(district_val)).first()
                if d:
                    ad.district = d.name
            elif district_val:
                ad.district = str(district_val).strip()

            if city_village_val:
                if str(city_village_val).isdigit():
                    cv = CityVillage.objects.filter(id=int(city_village_val)).first()
                    if cv:
                        ad.city_village = cv.name
                        if cv.settlement_type == 'village':
                            ad.is_village = True
                else:
                    ad.city_village = str(city_village_val).strip()

            ad.save()

            # Save uploaded images
            images = request.FILES.getlist('images')
            for i, img in enumerate(images):
                PropertyImage.objects.create(
                    advertisement=ad,
                    image=img,
                    is_main=(i == 0)
                )

            messages.success(request, 'آگهی املاک شما با موفقیت ثبت شد و در انتظار تایید مدیر سیستم است.')
            return redirect('main:my_property_ads')
    else:
        form = PropertyAdvertisementForm()

    context = {'form': form}
    return render(request, 'main/services/property-advertisement/step1.html', context)


def property_advertisement_step2(request):
    """Property advertisement step 2"""
    return render(request, 'main/services/property-advertisement/step2.html')


@login_required
def my_property_ads(request):
    """User's property advertisements"""
    user_ads = PropertyAdvertisement.objects.filter(user=request.user).order_by('-created_at')

    pending_count = user_ads.filter(status='pending').count()
    approved_count = user_ads.filter(status='approved').count()
    rejected_count = user_ads.filter(status='rejected').count()

    from django.core.paginator import Paginator
    paginator = Paginator(user_ads, 10)
    page_number = request.GET.get('page')
    ads_page = paginator.get_page(page_number)

    context = {
        'ads': ads_page,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
    }
    return render(request, 'main/my_property_ads.html', context)


@login_required
def edit_property_ad(request, ad_id):
    """Edit property advertisement"""
    ad = get_object_or_404(PropertyAdvertisement, id=ad_id, user=request.user)

    if request.method == 'POST':
        form = PropertyAdvertisementForm(request.POST, request.FILES, instance=ad)
        if form.is_valid():
            ad = form.save(commit=False)

            # Resolve numeric IDs to actual names
            province_val = form.cleaned_data.get('province') or request.POST.get('province')
            county_val = form.cleaned_data.get('county') or request.POST.get('county')
            district_val = form.cleaned_data.get('district') or request.POST.get('district')
            city_village_val = form.cleaned_data.get('city_village') or request.POST.get('city_village')

            if province_val and str(province_val).isdigit():
                p = Province.objects.filter(id=int(province_val)).first()
                if p:
                    ad.province = p.name
            elif province_val:
                ad.province = str(province_val).strip()

            if county_val and str(county_val).isdigit():
                c = County.objects.filter(id=int(county_val)).first()
                if c:
                    ad.county = c.name
            elif county_val:
                ad.county = str(county_val).strip()

            if district_val and str(district_val).isdigit():
                d = District.objects.filter(id=int(district_val)).first()
                if d:
                    ad.district = d.name
            elif district_val:
                ad.district = str(district_val).strip()

            if city_village_val:
                if str(city_village_val).isdigit():
                    cv = CityVillage.objects.filter(id=int(city_village_val)).first()
                    if cv:
                        ad.city_village = cv.name
                        if cv.settlement_type == 'village':
                            ad.is_village = True
                else:
                    ad.city_village = str(city_village_val).strip()

            # Set status to pending after edit for admin approval
            ad.status = 'pending'
            ad.save()

            # Save newly uploaded images
            images = request.FILES.getlist('images')
            for i, img in enumerate(images):
                PropertyImage.objects.create(
                    advertisement=ad,
                    image=img,
                    is_main=(ad.images.count() == 0 and i == 0)
                )

            messages.success(request, 'آگهی با موفقیت به‌روزرسانی شد و پس از بررسی مدیر فعال خواهد شد.')
            return redirect('main:my_property_ads')
    else:
        form = PropertyAdvertisementForm(instance=ad)

    context = {
        'form': form,
        'ad': ad,
    }
    return render(request, 'main/services/property-advertisement/edit_ad.html', context)


def view_property_ad(request, ad_id):
    """View property advertisement"""
    ad = get_object_or_404(PropertyAdvertisement, id=ad_id)
    # Only approved ads are public; owners and staff may preview their own/pending ones.
    if ad.status != 'approved':
        user = request.user
        if not (user.is_authenticated and (ad.user_id == user.id or user.is_staff)):
            raise Http404

    context = {
        'ad': ad,
        'property': ad,
        'images': ad.images.all(),
    }
    return render(request, 'main/services/property-advertisement/view_ad.html', context)
