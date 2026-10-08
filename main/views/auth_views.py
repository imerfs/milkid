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


def user_profile(request):
    """View user profile"""
    user_profile = request.user.profile
    
    context = {
        'user_profile': user_profile,
    }
    return render(request, 'main/user_profile.html', context)


def update_profile(request):
    """Update user profile"""
    user_profile = request.user.profile
    
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'پروفایل شما با موفقیت به‌روز شد.')
            return redirect('main:user_profile')
    else:
        form = ProfileUpdateForm(instance=user_profile)

    context = {
        'form': form,
        'user_profile': user_profile,
    }
    return render(request, 'main/update_profile.html', context)


def logout_view(request):
    """Logout user"""
    if hasattr(request, 'user') and request.user.is_authenticated:
        from django.core.cache import cache
        cache.delete(f'user_last_seen_{request.user.id}')
    logout(request)
    messages.success(request, 'با موفقیت از سیستم خارج شدید.')
    return redirect('main:login')


def register_choice(request):
    """Choose registration type"""
    return render(request, 'main/register_choice.html')


def register(request):
    """Register new citizen user"""
    if request.method == 'POST':
        form = CitizenRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Login user
            login(request, user)
            messages.success(request, 'حساب کاربری شما با موفقیت ایجاد شد.')
            return redirect('main:dashboard')
        else:
            messages.error(request, 'ثبت‌نام انجام نشد. لطفاً خطاهای مشخص‌شده در فرم را اصلاح نمایید.')
    else:
        form = CitizenRegistrationForm()

    context = {'form': form}
    return render(request, 'registration/register_citizen.html', context)


def pending_verification(request):
    """Pending verification page"""
    return render(request, 'main/pending_verification.html')


def access_blocked(request):
    """Access blocked / suspended notice page"""
    return render(request, 'main/access_blocked.html')


def register_municipality(request):
    """Register new municipality/dehyari"""
    if request.method == 'POST':
        form = MunicipalityRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            municipality = form.save(commit=False)
            municipality.status = 'pending'
            municipality.save()

            messages.success(request, 'درخواست ثبت شهرداری/دهیاری شما ثبت شد و در انتظار تایید مدیر سیستم است.')
            return redirect('main:home')
    else:
        form = MunicipalityRegistrationForm()

    context = {'form': form}
    return render(request, 'main/register_municipality.html', context)


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return '/dashboard/'

    def form_invalid(self, form):
        if getattr(form, 'is_blocked_user', False):
            return redirect('main:access_blocked')
        return super().form_invalid(form)


def staff_registration_info(request):
    """صفحه راهنمای ثبت‌نام کارمندان"""
    return render(request, 'main/staff_registration_info.html')


def register_role(request, role='dehyari'):
    """ثبت‌نام نقش‌های مختلف سامانه"""
    role_names = {
        'dehyari': 'دهیار',
        'engineer': 'مهندس / کارشناس فنی',
        'council': 'عضو شورا',
        'accountant': 'مسئول مالی',
        'inspector': 'ناظر فنی',
    }
    role_name = role_names.get(role, 'کارمند')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'درخواست ثبت‌نام شما به عنوان {role_name} با موفقیت ثبت شد و پس از بررسی توسط مدیر سامانه فعال خواهد شد.')
            return redirect('main:pending_verification')
    else:
        initial_data = {'role': role}
        form = CustomUserCreationForm(initial=initial_data)

    template_name = f'registration/register_{role}.html'
    context = {
        'form': form,
        'role': role,
        'role_name': role_name
    }
    return render(request, template_name, context)


def register_dehyari(request):
    """ثبت‌نام دهیار"""
    return register_role(request, role='dehyari')


def register_engineer(request):
    """ثبت‌نام مهندس/کارشناس فنی"""
    return register_role(request, role='engineer')


def register_council(request):
    """ثبت‌نام عضو شورا"""
    return register_role(request, role='council')


def register_accountant(request):
    """ثبت‌نام مسئول مالی"""
    return register_role(request, role='accountant')


def register_inspector(request):
    """ثبت‌نام ناظر فنی"""
    return register_role(request, role='inspector')
