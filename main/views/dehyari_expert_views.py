from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime
import json

from main.models import (
    UserProfile, ServiceRequest, RequestDocument, Notification,
    Inspection, TechnicalReport, Payment, Vote, CouncilComment,
    Municipality
)
from .common import role_required
from main import lifecycle
from main.access import policy_required
from main.gis.access import maps_for


def _json_body(request):
    """JSON body if present, else form data."""
    try:
        return json.loads(request.body)
    except Exception:
        return request.POST



@login_required
@ensure_csrf_cookie
@policy_required('request.update_status')
def dehyari_expert_dashboard(request):
    """
    جامع‌ترین داشبورد کارشناس دهیاری / کارشناس فنی
    کلیه درخواست‌های ثبت‌شده توسط شهروندان (به جز آگهی‌های ملک)
    به این پنل ارجاع شده و امکان ارجاع چندمرحله‌ای به شورا، ناظر، مالی و دهیار وجود دارد.
    """
    user_profile = getattr(request.user, 'profile', None)
    if not user_profile:
        return redirect('main:home')

    # دسترسی فقط برای کارشناس دهیاری (engineer)، ادمین و مدیران
    allowed_roles = ['engineer', 'admin', 'dehyari']
    if user_profile.role not in allowed_roles and not request.user.is_staff and not request.user.is_superuser:
        return HttpResponseForbidden("شما دسترسی لازم برای مشاهده پنل کارشناس دهیاری را ندارید.")

    # فیلتر جغرافیایی براساس حوزه دهیاری کاربر
    village_filter = Q()
    user_village = user_profile.city_village or user_profile.city_village_name
    if user_village and user_profile.role != 'admin':
        village_filter = (
            Q(city_village__name=user_village) |
            Q(user__profile__city_village_name=user_village) |
            Q(user__profile__city_village=user_profile.city_village)
        )

    # پایگاه کلی درخواست‌های شهروندان
    requests_qs = ServiceRequest.objects.filter(village_filter).select_related(
        'user', 'user__profile', 'service', 'city_village', 'assigned_to'
    ).prefetch_related('documents', 'technical_reports', 'inspections').order_by('-created_at')

    # در صورتی که فیلتر حوزه اختصاصی رکوردی نداشت، کلیه درخواست‌ها را برای دیده‌شدن نمایش می‌دهیم
    if not requests_qs.exists() and village_filter != Q():
        requests_qs = ServiceRequest.objects.all().select_related(
            'user', 'user__profile', 'service', 'city_village', 'assigned_to'
        ).prefetch_related('documents', 'technical_reports', 'inspections').order_by('-created_at')

    # آمار تفکیکی
    total_count = requests_qs.count()
    expert_pending_count = requests_qs.filter(workflow_stage='expert_review', status__in=['pending', 'in_review']).count()
    council_review_count = requests_qs.filter(workflow_stage='council_review').count()
    inspection_count = requests_qs.filter(workflow_stage='inspection').count()
    finance_count = requests_qs.filter(workflow_stage='finance_review').count()
    mayor_review_count = requests_qs.filter(workflow_stage='mayor_review').count()
    approved_count = requests_qs.filter(status__in=['approved', 'completed']).count()
    rejected_count = requests_qs.filter(status='rejected').count()
    requires_docs_count = requests_qs.filter(status='requires_documents').count()
    in_referral_total = council_review_count + inspection_count + finance_count + mayor_review_count

    stats = {
        'total_requests': total_count,
        'expert_pending': expert_pending_count,
        'in_referral': in_referral_total,
        'council_count': council_review_count,
        'inspection_count': inspection_count,
        'finance_count': finance_count,
        'mayor_count': mayor_review_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'requires_docs_count': requires_docs_count,
    }

    # همکاران دهیاری در این منطقه جهت ارجاع سریع
    peer_filter = Q()
    if user_village:
        peer_filter = Q(city_village_name=user_village) | Q(city_village=user_profile.city_village)

    council_members = UserProfile.objects.filter(peer_filter, role='council', is_active=True).select_related('user')
    inspectors = UserProfile.objects.filter(peer_filter, role='inspector', is_active=True).select_related('user')
    accountants = UserProfile.objects.filter(peer_filter, role='accountant', is_active=True).select_related('user')
    dehyars = UserProfile.objects.filter(peer_filter, role='dehyari', is_active=True).select_related('user')

    # در صورت خالی بودن، تمام کاربران فعال با این نقش‌ها
    if not council_members.exists():
        council_members = UserProfile.objects.filter(role='council', is_active=True).select_related('user')[:5]
    if not inspectors.exists():
        inspectors = UserProfile.objects.filter(role='inspector', is_active=True).select_related('user')[:5]
    if not accountants.exists():
        accountants = UserProfile.objects.filter(role='accountant', is_active=True).select_related('user')[:5]
    if not dehyars.exists():
        dehyars = UserProfile.objects.filter(role='dehyari', is_active=True).select_related('user')[:5]

    # لیست کامل درخواست‌ها جهت نمایش در جدول
    requests_list = list(requests_qs)

    # اعلانات خوانده‌نشده کارشناس
    unread_notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:8]

    context = {
        'user_profile': user_profile,
        'stats': stats,
        'requests': requests_list,
        'council_members': council_members,
        'inspectors': inspectors,
        'accountants': accountants,
        'dehyars': dehyars,
        'unread_notifications': unread_notifications,
        'user_village': user_village or 'حوزه دهیاری مرکزی',
        'gis_maps': maps_for(request.user),     # village maps this user may open (technical expert / admin)
    }

    return render(request, 'main/dashboards/dehyari_expert_dashboard.html', context)


@login_required
@policy_required('request.update_status', api=True)
def api_expert_request_details(request, request_id):
    """دریافت جزییات کامل پرونده، فرم‌ها، مدارک و سوابق جهت نمایش در مدال کارشناس"""
    try:
        service_request = get_object_or_404(ServiceRequest, id=request_id)
        u = service_request.user
        prof = getattr(u, 'profile', None)

        docs = []
        for d in service_request.documents.all():
            docs.append({
                'id': d.id,
                'name': d.document_name,
                'url': d.document.url if d.document else '',
                'uploaded_at': d.uploaded_at.strftime('%Y/%m/%d %H:%M') if d.uploaded_at else ''
            })

        inspections = []
        for insp in service_request.inspections.all():
            inspections.append({
                'id': insp.id,
                'inspector_name': insp.inspector.get_full_name() or insp.inspector.username,
                'status': insp.get_status_display(),
                'is_approved': insp.is_approved,
                'report': insp.report,
                'date': insp.inspection_date.strftime('%Y/%m/%d') if insp.inspection_date else insp.created_at.strftime('%Y/%m/%d')
            })

        reports = []
        for rep in service_request.technical_reports.all():
            reports.append({
                'id': rep.id,
                'title': rep.title,
                'report_type': rep.get_report_type_display(),
                'engineer_name': rep.engineer.get_full_name() or rep.engineer.username,
                'content': rep.content,
                'recommendations': rep.recommendations,
                'doc_url': rep.document.url if rep.document else '',
                'created_at': rep.created_at.strftime('%Y/%m/%d %H:%M')
            })

        votes = []
        for v in service_request.votes.all():
            votes.append({
                'council_member': v.council_member.get_full_name() or v.council_member.username,
                'vote': v.get_vote_display(),
                'reason': v.reason,
                'voted_at': v.voted_at.strftime('%Y/%m/%d %H:%M')
            })

        return JsonResponse({
            'success': True,
            'request': {
                'id': service_request.id,
                'title': service_request.title,
                'request_type': service_request.request_type,
                'request_type_display': service_request.get_request_type_display(),
                'description': service_request.description,
                'status': service_request.status,
                'status_display': service_request.get_status_display(),
                'workflow_stage': service_request.workflow_stage,
                'workflow_stage_display': service_request.get_workflow_stage_display(),
                'referral_target': service_request.referral_target,
                'referral_target_display': service_request.get_referral_target_display() if hasattr(service_request, 'get_referral_target_display') else service_request.referral_target,
                'referral_notes': service_request.referral_notes or '',
                'referral_date': service_request.referral_date.strftime('%Y/%m/%d %H:%M') if service_request.referral_date else '',
                'created_at': service_request.created_at.strftime('%Y/%m/%d %H:%M'),
                'property_address': service_request.property_address or '',
                'property_area': str(service_request.property_area or ''),
                'property_usage': service_request.property_usage or '',
                'deed_number': service_request.deed_number or '',
                'parcel_number': service_request.parcel_number or '',
                'city_village': str(service_request.city_village or prof.city_village_name if prof else ''),
                'form_data': service_request.form_data or {},
                'workflow_history': service_request.workflow_history or [],
                'staff_comments': service_request.staff_comments or '',
            },
            'applicant': {
                'name': u.get_full_name() or u.username,
                'username': u.username,
                'mobile': prof.mobile_number if prof else '',
                'national_id': prof.national_id if prof else '',
            },
            'documents': docs,
            'inspections': inspections,
            'technical_reports': reports,
            'council_votes': votes,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
@policy_required('request.update_status', api=True)
def api_expert_forward_request(request, request_id):
    """
    ارجاع درخواست توسط کارشناس دهیاری به پنل مقصد:
    شورا (council)، ناظر فنی (inspector)، مسئول مالی (accountant)، دهیار (dehyari)
    """
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    body = _json_body(request)
    target_role = body.get('target_role') or body.get('referral_target')
    notes = (body.get('notes') or '').strip()
    if not target_role:
        return JsonResponse({'success': False, 'message': 'لطفاً پنل / نقش مقصد را انتخاب کنید.'}, status=400)
    assigned_user = User.objects.filter(id=body.get('assigned_user_id')).first() if body.get('assigned_user_id') else None
    try:
        new_stage, target_name = lifecycle.refer(
            service_request, request.user, target_role, notes=notes, assigned_user=assigned_user)
    except lifecycle.TransitionError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'message': f'پرونده با موفقیت به «{target_name}» ارجاع گردید.',
        'request_id': service_request.id,
        'new_stage': new_stage,
        'new_stage_display': service_request.get_workflow_stage_display(),
        'target_role': target_role,
    })


@login_required
@require_http_methods(["POST"])
@policy_required('request.update_status', api=True)
def api_expert_approve_direct(request, request_id):
    """تایید مستقیم پرونده یا تایید مرحله کارشناسی"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    body = _json_body(request)
    completed = bool(body.get('mark_as_completed', False))
    try:
        lifecycle.approve(service_request, request.user,
                          notes=(body.get('notes') or '').strip(), completed=completed)
    except lifecycle.TransitionError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=409)
    msg = ('پرونده با موفقیت تایید نهایی و تکمیل گردید.' if completed
           else 'تاییدیه کارشناسی با موفقیت برای این پرونده ثبت گردید.')
    return JsonResponse({'success': True, 'message': msg})


@login_required
@require_http_methods(["POST"])
@policy_required('request.update_status', api=True)
def api_expert_request_documents(request, request_id):
    """اعلام نیاز به تکمیل مدارک به متقاضی"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    notes = (_json_body(request).get('notes') or '').strip()
    if not notes:
        return JsonResponse({'success': False, 'message': 'لطفاً مدارک مورد نیاز یا توضیحات نقص پرونده را درج نمایید.'}, status=400)
    try:
        lifecycle.request_documents(service_request, request.user, notes)
    except lifecycle.TransitionError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=409)
    return JsonResponse({'success': True, 'message': 'اعلام نقص مدارک با موفقیت به متقاضی اطلاع داده شد.'})


@login_required
@require_http_methods(["POST"])
@policy_required('request.update_status', api=True)
def api_expert_reject_request(request, request_id):
    """رد درخواست توسط کارشناس با ذکر دلیل"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    reason = (_json_body(request).get('reason') or '').strip()
    if not reason:
        return JsonResponse({'success': False, 'message': 'لطفاً دلیل رد درخواست را وارد نمایید.'}, status=400)
    try:
        lifecycle.reject(service_request, request.user, reason)
    except lifecycle.TransitionError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=409)
    return JsonResponse({'success': True, 'message': 'درخواست با موفقیت رد گردید.'})


@login_required
@require_http_methods(["POST"])
@policy_required('request.update_status', api=True)
def api_expert_add_technical_report(request, request_id):
    """ثبت گزارش فنی کارشناسی برای پرونده"""
    try:
        service_request = get_object_or_404(ServiceRequest, id=request_id)
        try:
            body = json.loads(request.body)
        except Exception:
            body = request.POST

        title = body.get('title') or request.POST.get('title', 'گزارش کارشناسی فنی')
        report_type = body.get('report_type') or request.POST.get('report_type', 'technical_review')
        content = (body.get('content') or request.POST.get('content', '')).strip()
        recommendations = (body.get('recommendations') or request.POST.get('recommendations', '')).strip()
        uploaded_doc = request.FILES.get('document')

        if not content:
            return JsonResponse({'success': False, 'message': 'متن گزارش فنی نمی‌تواند خالی باشد.'}, status=400)

        rep = TechnicalReport.objects.create(
            request=service_request,
            engineer=request.user,
            report_type=report_type,
            title=title,
            content=content,
            recommendations=recommendations,
            document=uploaded_doc
        )

        service_request.add_workflow_step(
            action=f'ثبت گزارش فنی: {title}',
            from_user=request.user,
            to_role='engineer',
            notes=content[:100]
        )
        service_request.save()

        return JsonResponse({
            'success': True,
            'message': 'گزارش فنی کارشناسی با موفقیت ثبت گردید.',
            'report_id': rep.id
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
