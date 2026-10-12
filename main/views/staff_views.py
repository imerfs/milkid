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
from main import lifecycle
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


@policy_required('staff.any')
def staff_dashboard(request):
    """Enhanced dashboard for staff members"""
    user_profile = request.user.profile

    # Get recent requests for review
    recent_requests = ServiceRequest.objects.all().order_by('-created_at')[:10]

    # Get requests assigned to this staff member
    my_assignments = ServiceRequest.objects.filter(assigned_to=request.user).exclude(status='completed')

    # Get inspections assigned to this user
    my_inspections = Inspection.objects.filter(inspector=request.user).exclude(status='completed').order_by('-created_at')[:5]
    
    # Get violations assigned to this user
    my_violations = ViolationReport.objects.filter(assigned_to=request.user).exclude(status='resolved').order_by('-created_at')[:5]
    
    # Get technical reports created by this user
    my_reports = TechnicalReport.objects.filter(engineer=request.user).order_by('-created_at')[:5]

    # Statistics
    stats = {
        'total_requests': ServiceRequest.objects.count(),
        'pending_requests': ServiceRequest.objects.filter(status='pending').count(),
        'in_review': ServiceRequest.objects.filter(status='in_review').count(),
        'my_assignments': my_assignments.count(),
        'completed_today': ServiceRequest.objects.filter(
            status='completed',
            updated_at__date=timezone.now().date()
        ).count(),
        'pending_inspections': Inspection.objects.filter(inspector=request.user, status='pending').count(),
        'my_violations': ViolationReport.objects.filter(assigned_to=request.user).exclude(status='resolved').count(),
        'my_reports_count': TechnicalReport.objects.filter(engineer=request.user).count(),
    }

    context = {
        'user_profile': user_profile,
        'recent_requests': recent_requests,
        'my_assignments': my_assignments,
        'my_inspections': my_inspections,
        'my_violations': my_violations,
        'my_reports': my_reports,
        'stats': stats,
    }
    return render(request, 'main/dashboards/staff_dashboard.html', context)


@policy_required('staff.engineer')
def engineer_dashboard(request):
    """Dashboard for engineer (کارشناس فنی)"""
    user_profile = request.user.profile
    
    # Get requests assigned to this engineer
    my_assignments = ServiceRequest.objects.filter(assigned_to=request.user).exclude(status='completed').order_by('-created_at')
    
    # Get all pending technical requests
    pending_technical = ServiceRequest.objects.filter(
        request_type__in=['building_permit', 'no_permit', 'land_use_change'],
        status__in=['pending', 'in_review']
    ).order_by('-created_at')[:10]
    
    # Get inspections created by this engineer
    my_inspections = Inspection.objects.filter(inspector=request.user).order_by('-created_at')[:5]
    
    # Get violations assigned to this engineer
    my_violations = ViolationReport.objects.filter(assigned_to=request.user).exclude(status='resolved').order_by('-created_at')[:5]
    
    # Get technical reports created by this engineer
    my_reports = TechnicalReport.objects.filter(engineer=request.user).order_by('-created_at')[:5]
    
    # Recent notifications
    recent_notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5]
    
    # Statistics
    stats = {
        'my_assignments': my_assignments.count(),
        'pending_review': ServiceRequest.objects.filter(status='in_review').count(),
        'completed_this_month': ServiceRequest.objects.filter(
            status='completed',
            updated_at__month=timezone.now().month
        ).count(),
        'total_requests': ServiceRequest.objects.count(),
        'pending_inspections': Inspection.objects.filter(inspector=request.user, status='pending').count(),
        'my_violations': ViolationReport.objects.filter(assigned_to=request.user).exclude(status='resolved').count(),
        'total_reports': TechnicalReport.objects.filter(engineer=request.user).count(),
    }
    
    context = {
        'user_profile': user_profile,
        'my_assignments': my_assignments,
        'pending_technical': pending_technical,
        'my_inspections': my_inspections,
        'my_violations': my_violations,
        'my_reports': my_reports,
        'recent_notifications': recent_notifications,
        'stats': stats,
    }
    return render(request, 'main/dashboards/Municipal technical experts.html', context)


@policy_required('staff.inspector')
def inspector_dashboard(request):
    """Dashboard for inspector (ناظر فنی)"""
    user_profile = request.user.profile
    
    # Get inspection assignments for this inspector
    my_inspections = Inspection.objects.filter(inspector=request.user).order_by('-created_at')
    pending_inspections = my_inspections.filter(status='pending')[:10]
    
    # Get service request assignments
    inspection_assignments = ServiceRequest.objects.filter(
        request_type__in=['building_permit', 'no_permit'],
        status='approved'
    ).order_by('-updated_at')[:10]
    
    # Get violations assigned to this inspector
    my_violations = ViolationReport.objects.filter(assigned_to=request.user).exclude(status='resolved').order_by('-created_at')[:5]
    
    # Get technical reports created by this inspector
    my_reports = TechnicalReport.objects.filter(engineer=request.user).order_by('-created_at')[:5]
    
    # Recent notifications
    recent_notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5]
    
    # Statistics
    stats = {
        'pending_inspections': my_inspections.filter(status='pending').count(),
        'in_progress_inspections': my_inspections.filter(status='in_progress').count(),
        'completed_inspections': my_inspections.filter(status='completed').count(),
        'total_projects': Property.objects.count(),
        'my_violations': ViolationReport.objects.filter(assigned_to=request.user).exclude(status='resolved').count(),
        'total_reports': TechnicalReport.objects.filter(engineer=request.user).count(),
    }
    
    context = {
        'user_profile': user_profile,
        'my_inspections': pending_inspections,
        'inspection_assignments': inspection_assignments,
        'my_violations': my_violations,
        'my_reports': my_reports,
        'recent_notifications': recent_notifications,
        'stats': stats,
    }
    return render(request, 'main/dashboards/Technical supervisor.html', context)


# Menu entries of the accountant page that are not built yet; shown disabled.
ACCOUNTANT_SOON = []


@policy_required('staff.accountant')
def accountant_dashboard(request):
    """Dashboard for financial manager (مسئول مالی): one page; the workspace loads from main/views/accounting_panel."""
    from main.models import Notification
    from main.accounting import ledger
    from main.office.errors import OfficeError

    # The workspace needs a municipality; without one the page says so instead of failing.
    try:
        acc_muni_name = ledger.municipality_of(request.user).name
    except OfficeError:
        acc_muni_name = None
    return render(request, 'main/dashboards/accountant.html', {
        'acc_ready': acc_muni_name is not None,
        'acc_muni_name': acc_muni_name or '',
        'user_profile': request.user.profile,
        'notifications': Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5],
        'acc_soon': ACCOUNTANT_SOON,
    })


@policy_required('staff.any')
def inspection_list(request):
    """List all inspections assigned to current user"""
    user_profile = request.user.profile
    
    inspections = Inspection.objects.filter(inspector=request.user).order_by('-created_at')
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        inspections = inspections.filter(status=status_filter)
    
    stats = {
        'total': Inspection.objects.filter(inspector=request.user).count(),
        'pending': Inspection.objects.filter(inspector=request.user, status='pending').count(),
        'in_progress': Inspection.objects.filter(inspector=request.user, status='in_progress').count(),
        'completed': Inspection.objects.filter(inspector=request.user, status='completed').count(),
    }
    
    context = {
        'user_profile': user_profile,
        'inspections': inspections,
        'stats': stats,
        'status_filter': status_filter,
    }
    return render(request, 'main/technical/inspection_list.html', context)


@policy_required('staff.any')
def inspection_detail(request, inspection_id):
    """View and update inspection details"""
    inspection = get_object_or_404(Inspection, id=inspection_id, inspector=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_report':
            inspection.report = request.POST.get('report', '')
            inspection.notes = request.POST.get('notes', '')
            inspection.status = 'in_progress'
            inspection.save()
            messages.success(request, 'گزارش بازرسی به‌روز شد.')
            
        elif action == 'complete':
            inspection.report = request.POST.get('report', '')
            inspection.is_approved = True
            inspection.status = 'completed'
            inspection.completed_at = timezone.now()
            inspection.save()
            
            lifecycle.record_inspection(inspection.request, request.user, approved=True)
            messages.success(request, 'بازرسی با موفقیت تکمیل شد.')
            
        elif action == 'reject':
            inspection.rejection_reason = request.POST.get('rejection_reason', '')
            inspection.status = 'rejected'
            inspection.completed_at = timezone.now()
            inspection.save()
            
            lifecycle.record_inspection(inspection.request, request.user, approved=False,
                                        reason=inspection.rejection_reason)
            messages.warning(request, 'بازرسی رد شد.')
            
        elif action == 'upload_document':
            document = request.FILES.get('document')
            document_type = request.POST.get('document_type')
            description = request.POST.get('description', '')
            
            if document and document_type:
                InspectionDocument.objects.create(
                    inspection=inspection,
                    document=document,
                    document_type=document_type,
                    description=description
                )
                messages.success(request, 'مدرک با موفقیت آپلود شد.')
        
        return redirect('main:inspection_detail', inspection_id=inspection.id)
    
    documents = inspection.documents.all()
    
    context = {
        'user_profile': request.user.profile,
        'inspection': inspection,
        'documents': documents,
    }
    return render(request, 'main/technical/inspection_detail.html', context)


@policy_required('staff.any')
def violation_list(request):
    """List violations assigned to current user"""
    user_profile = request.user.profile
    
    violations = ViolationReport.objects.filter(assigned_to=request.user).order_by('-created_at')
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        violations = violations.filter(status=status_filter)
    
    stats = {
        'total': ViolationReport.objects.filter(assigned_to=request.user).count(),
        'pending': ViolationReport.objects.filter(assigned_to=request.user, status='pending').count(),
        'investigating': ViolationReport.objects.filter(assigned_to=request.user, status='investigating').count(),
        'resolved': ViolationReport.objects.filter(assigned_to=request.user, status='resolved').count(),
    }
    
    context = {
        'user_profile': user_profile,
        'violations': violations,
        'stats': stats,
        'status_filter': status_filter,
    }
    return render(request, 'main/technical/violation_list.html', context)


@policy_required('staff.any')
def violation_detail(request, violation_id):
    """View and update violation details"""
    violation = get_object_or_404(ViolationReport, id=violation_id)
    
    if violation.assigned_to and violation.assigned_to != request.user:
        messages.error(request, 'شما دسترسی به این تخلف را ندارید.')
        return redirect('main:violation_list')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            violation.status = request.POST.get('status')
            violation.response = request.POST.get('response', '')
            
            if violation.status == 'resolved':
                violation.resolved_at = timezone.now()
            
            violation.save()
            
            Notification.objects.create(
                user=violation.reporter,
                notification_type='violation_report',
                title='به‌روزرسانی وضعیت تخلف',
                message=f'وضعیت گزارش تخلف {violation.title} به‌روز شد.'
            )
            messages.success(request, 'وضعیت تخلف به‌روز شد.')
            
        elif action == 'add_technical_report':
            title = request.POST.get('report_title')
            content = request.POST.get('report_content')
            recommendations = request.POST.get('recommendations', '')
            document = request.FILES.get('document')
            
            if title and content:
                TechnicalReport.objects.create(
                    violation=violation,
                    engineer=request.user,
                    report_type='violation',
                    title=title,
                    content=content,
                    recommendations=recommendations,
                    document=document
                )
                violation.status = 'investigating'
                violation.save()
                messages.success(request, 'گزارش فنی با موفقیت ثبت شد.')
        
        return redirect('main:violation_detail', violation_id=violation.id)
    
    technical_reports = violation.technical_reports.all()
    
    context = {
        'user_profile': request.user.profile,
        'violation': violation,
        'technical_reports': technical_reports,
    }
    return render(request, 'main/technical/violation_detail.html', context)


@policy_required('staff.any')
def technical_report_create(request):
    """Create a new technical report"""
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        report_type = request.POST.get('report_type')
        title = request.POST.get('title')
        content = request.POST.get('content')
        recommendations = request.POST.get('recommendations', '')
        document = request.FILES.get('document')
        
        if request_id and report_type and title and content:
            service_request = get_object_or_404(ServiceRequest, id=request_id)
            
            TechnicalReport.objects.create(
                request=service_request,
                engineer=request.user,
                report_type=report_type,
                title=title,
                content=content,
                recommendations=recommendations,
                document=document
            )
            
            Notification.objects.create(
                user=service_request.user,
                notification_type='request_status',
                title='گزارش فنی جدید',
                message=f'گزارش فنی جدید برای درخواست {service_request.title} ثبت شد.',
                related_request=service_request
            )
            
            messages.success(request, 'گزارش فنی با موفقیت ثبت شد.')
            return redirect('main:technical_report_list')
        else:
            messages.error(request, 'لطفا تمامی فیلدهای الزامی را پر کنید.')
    
    my_requests = ServiceRequest.objects.filter(assigned_to=request.user)
    
    context = {
        'user_profile': request.user.profile,
        'my_requests': my_requests,
    }
    return render(request, 'main/technical/report_create.html', context)


@policy_required('staff.any')
def technical_report_list(request):
    """List all technical reports created by current user"""
    reports = TechnicalReport.objects.filter(engineer=request.user).order_by('-created_at')
    
    report_type_filter = request.GET.get('type', '')
    if report_type_filter:
        reports = reports.filter(report_type=report_type_filter)
    
    stats = {
        'total': TechnicalReport.objects.filter(engineer=request.user).count(),
        'inspection': TechnicalReport.objects.filter(engineer=request.user, report_type='inspection').count(),
        'violation': TechnicalReport.objects.filter(engineer=request.user, report_type='violation').count(),
        'technical_review': TechnicalReport.objects.filter(engineer=request.user, report_type='technical_review').count(),
    }
    
    context = {
        'user_profile': request.user.profile,
        'reports': reports,
        'stats': stats,
        'report_type_filter': report_type_filter,
    }
    return render(request, 'main/technical/report_list.html', context)


@policy_required('staff.any')
def technical_report_detail(request, report_id):
    """View technical report details"""
    report = get_object_or_404(TechnicalReport, id=report_id, engineer=request.user)
    
    context = {
        'user_profile': request.user.profile,
        'report': report,
    }
    return render(request, 'main/technical/report_detail.html', context)


@policy_required('staff.any')
def technical_report_export(request):
    """Export technical reports to PDF or Excel"""
    from django.http import HttpResponse
    import io
    
    report_type = request.GET.get('type', '')
    export_format = request.GET.get('format', 'excel')
    
    reports = TechnicalReport.objects.filter(engineer=request.user)
    if report_type:
        reports = reports.filter(report_type=report_type)
    
    if export_format == 'excel':
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Fill, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
            
            wb = Workbook()
            ws = wb.active
            ws.title = 'گزارش‌های فنی'
            
            headers = ['ردیف', 'عنوان', 'نوع گزارش', 'درخواست', 'تاریخ ثبت']
            header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF')
            
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            for idx, report in enumerate(reports, start=2):
                ws.cell(row=idx, column=1, value=idx-1)
                ws.cell(row=idx, column=2, value=report.title)
                ws.cell(row=idx, column=3, value=report.get_report_type_display())
                ws.cell(row=idx, column=4, value=report.request.title if report.request else '-')
                ws.cell(row=idx, column=5, value=report.created_at.strftime('%Y/%m/%d'))
            
            for col in range(1, len(headers) + 1):
                ws.column_dimensions[get_column_letter(col)].width = 20
            
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename=technical_reports.xlsx'
            return response
        except Exception as e:
            messages.error(request, f'خطا در ایجاد فایل اکسل: {str(e)}')
            return redirect('main:technical_report_list')
    
    messages.error(request, 'فرمت export نامعتبر است.')
    return redirect('main:technical_report_list')


@policy_required('request.update_status')
def assign_request_to_engineer(request, request_id):
    """Assign a request to an engineer"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    if request.method == 'POST':
        engineer_id = request.POST.get('engineer_id')
        
        if engineer_id:
            engineer = get_object_or_404(User, id=engineer_id, profile__role='engineer')
            service_request.assigned_to = engineer
            service_request.status = 'in_review'
            service_request.save()
            
            Notification.objects.create(
                user=engineer,
                notification_type='request_status',
                title='درخواست جدید',
                message=f'درخواست {service_request.title} به شما ارجاع شد.',
                related_request=service_request
            )
            
            messages.success(request, f'درخواست به {engineer.get_full_name()} ارجاع شد.')
            return redirect('main:manage_requests')
    
    engineers = UserProfile.objects.filter(role='engineer', is_verified=True)
    
    context = {
        'user_profile': request.user.profile,
        'service_request': service_request,
        'engineers': engineers,
    }
    return render(request, 'main/technical/assign_request.html', context)


@policy_required('staff.any')
def create_inspection(request, request_id):
    """Create a new inspection for a request"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    if request.method == 'POST':
        inspector_id = request.POST.get('inspector_id')
        inspection_date = request.POST.get('inspection_date')
        notes = request.POST.get('notes', '')
        
        if inspector_id:
            inspector = get_object_or_404(User, id=inspector_id, profile__role__in=['engineer', 'inspector'])
            
            inspection = Inspection.objects.create(
                request=service_request,
                inspector=inspector,
                inspection_date=inspection_date if inspection_date else None,
                notes=notes
            )
            
            Notification.objects.create(
                user=inspector,
                notification_type='request_status',
                title='بازرسی جدید',
                message=f'بازرسی جدید برای درخواست {service_request.title} به شما ارجاع شد.',
                related_request=service_request
            )
            
            messages.success(request, 'بازرسی با موفقیت ایجاد شد.')
            return redirect('main:engineer_dashboard')
    
    inspectors = UserProfile.objects.filter(role__in=['engineer', 'inspector'], is_verified=True)
    
    context = {
        'user_profile': request.user.profile,
        'service_request': service_request,
        'inspectors': inspectors,
    }
    return render(request, 'main/technical/create_inspection.html', context)
