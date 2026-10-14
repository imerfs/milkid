"""Email login codes, the support form, the admin mailbox and the SMS settings.

The mailbox and SMS settings are admin-only (policy ``admin.manage``); every mutation is a POST and is
written to the security log with the acting admin.
"""
import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from main import logincode, mailbox, sms
from main.access import policy_required
from main.models import MailMessage, SmsConfig
from main.views.admin_views import admin_dashboard

audit = logging.getLogger('django.security.serverpanel')
GENERIC = 'اگر این ایمیل به یک حساب فعال تعلق داشته باشد، کد ورود برای آن فرستاده شد.'
SESSION_EMAIL = 'login_code_email'
FOLDERS = ('inbox', 'sent', 'trash')


# ---- login by emailed code ----

def login_code_request(request):
    if request.user.is_authenticated:
        return redirect('main:dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()[:254]
        logincode.issue(email)
        request.session[SESSION_EMAIL] = email
        messages.info(request, GENERIC)
        return redirect('main:login_code_verify')
    return render(request, 'registration/login_code_request.html')


def login_code_verify(request):
    if request.user.is_authenticated:
        return redirect('main:dashboard')
    email = request.session.get(SESSION_EMAIL, '')
    if not email:
        return redirect('main:login_code_request')
    if request.method == 'POST':
        user = logincode.verify(email, request.POST.get('code', ''))
        if user is not None:
            request.session.pop(SESSION_EMAIL, None)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('main:dashboard')
        messages.error(request, 'کد نادرست یا منقضی است.')
    return render(request, 'registration/login_code_verify.html', {'email': email})


# ---- support form (any signed-in user writes to the admin mailbox) ----

@login_required
def support(request):
    if request.method == 'POST':
        subject, body = request.POST.get('subject', '').strip(), request.POST.get('body', '').strip()
        if not subject or not body or len(subject) > 200 or len(body) > mailbox.MAX_BODY:
            messages.error(request, 'موضوع (حداکثر ۲۰۰ نویسه) و متن پیام (حداکثر ۲۰٬۰۰۰ نویسه) لازم است.')
            return render(request, 'main/support.html', {'subject': subject, 'body': body})
        sender = request.user.email or f'{request.user.username}@users.invalid'
        MailMessage.objects.create(folder='inbox', source='support', sender=sender, subject=subject, body=body,
                                   user=request.user)
        if settings.SITE_EMAIL:
            send_mail(f'[پشتیبانی] {subject}', f'از: {request.user.get_full_name() or request.user.username} <{sender}>\n\n{body}',
                      None, [settings.SITE_EMAIL], fail_silently=True)
        messages.success(request, 'پیام شما برای پشتیبانی ثبت شد. پاسخ از طریق ایمیل حساب شما داده می‌شود.')
        return redirect('main:support')
    return render(request, 'main/support.html')


# ---- admin mailbox ----

def _mail_back(folder='inbox', **query):
    return redirect(f"{reverse('main:admin_mail')}?{urlencode({'folder': folder, **query})}")


@policy_required('admin.manage')
def admin_mail(request):
    folder = request.GET.get('folder') if request.GET.get('folder') in FOLDERS else 'inbox'
    q = request.GET.get('q', '').strip()[:100]
    items = MailMessage.objects.filter(folder=folder)
    if q:
        items = items.filter(Q(subject__icontains=q) | Q(sender__icontains=q) | Q(recipients__icontains=q) | Q(body__icontains=q))
    selected = None
    if request.GET.get('id', '').isdigit():
        selected = MailMessage.objects.filter(id=request.GET['id']).first()
        if selected and not selected.is_read:
            MailMessage.objects.filter(id=selected.id).update(is_read=True)
            selected.is_read = True
    compose = {}
    if request.GET.get('compose') == '1':
        compose = {'open': True}
        reply = MailMessage.objects.filter(id=request.GET.get('reply', 0) or 0).first() if request.GET.get('reply', '').isdigit() else None
        if reply:
            target = reply.sender if reply.folder != 'sent' else reply.recipients
            if reply.user_id and reply.user.email:
                target = reply.user.email
            subject = reply.subject if reply.subject.lower().startswith('re:') else f'Re: {reply.subject}'
            quoted = '\n'.join('> ' + line for line in reply.body.splitlines()[:20])
            compose.update(to=target, subject=subject[:200], body=f'\n\n{quoted}')
    page = Paginator(items, 40).get_page(request.GET.get('page'))
    ctx = {'mail_open': True, 'mail_folder': folder, 'mail_page': page, 'mail_q': q, 'mail_selected': selected,
           'mail_compose': compose, 'mail_unread': MailMessage.objects.filter(folder='inbox', is_read=False).count(),
           'mail_trash': MailMessage.objects.filter(folder='trash').count(),
           'imap_ready': mailbox.imap_configured(), 'mail_from': settings.DEFAULT_FROM_EMAIL}
    return admin_dashboard(request, server_panel=ctx)


@policy_required('admin.manage')
@require_POST
def admin_mail_send(request):
    try:
        record = mailbox.send(request.POST.get('to', ''), request.POST.get('subject', ''), request.POST.get('body', ''),
                              user=request.user)
    except ValueError as error:
        messages.error(request, str(error))
        return _mail_back('inbox', compose=1)
    audit.warning('mailbox: %s sent mail to %s (failed=%s)', request.user.username, record.recipients, record.failed)
    if record.failed:
        messages.error(request, f'ارسال ناموفق بود؛ پیام در «ارسال‌شده» نگه داشته شد. {record.error}')
    else:
        messages.success(request, 'ایمیل ارسال شد.')
    return _mail_back('sent', id=record.id)


@policy_required('admin.manage')
@require_POST
def admin_mail_action(request):
    folder = request.POST.get('folder') if request.POST.get('folder') in FOLDERS else 'inbox'
    ids = [int(i) for i in request.POST.getlist('ids') if i.isdigit()][:100]
    rows = MailMessage.objects.filter(id__in=ids)
    op = request.POST.get('op')
    if op == 'trash':
        for row in rows.exclude(folder='trash'):
            MailMessage.objects.filter(id=row.id).update(prev_folder=row.folder, folder='trash')
    elif op == 'restore':
        for row in rows.filter(folder='trash'):
            MailMessage.objects.filter(id=row.id).update(folder=row.prev_folder or 'inbox', prev_folder='')
    elif op == 'delete':
        rows.filter(folder='trash').delete()
        audit.warning('mailbox: %s deleted %d messages for good', request.user.username, len(ids))
    elif op in ('read', 'unread'):
        rows.update(is_read=(op == 'read'))
    else:
        messages.error(request, 'عملیات نامعتبر است.')
    return _mail_back(folder)


@policy_required('admin.manage')
@require_POST
def admin_mail_fetch(request):
    try:
        new = mailbox.fetch_imap()
    except ValueError as error:
        messages.error(request, str(error))
    else:
        audit.warning('mailbox: %s fetched mail, %d new', request.user.username, new)
        messages.success(request, f'{new} ایمیل جدید دریافت شد.')
    return _mail_back('inbox')


# ---- SMS settings (a tab of the server panel) ----

def _sms_back():
    return redirect(f"{reverse('main:admin_server')}?{urlencode({'tab': 'sms'})}")


@policy_required('admin.manage')
@require_POST
def admin_sms_save(request):
    config = sms.get_config()
    url = request.POST.get('base_url', '').strip()[:300]
    if url:
        error = sms.check_url(url)
        if error:
            messages.error(request, error)
            return _sms_back()
    config.base_url = url
    config.sender = request.POST.get('sender', '').strip()[:40]
    for field in ('auth_header', 'to_field', 'text_field', 'sender_field'):
        value = request.POST.get(field, '').strip()[:40]
        if not value or not value.replace('-', '').replace('_', '').isalnum() or not value.isascii():
            messages.error(request, 'نام فیلدها و هدر فقط می‌تواند حرف انگلیسی، عدد، خط تیره و زیرخط باشد.')
            return _sms_back()
        setattr(config, field, value)
    config.auth_prefix = request.POST.get('auth_prefix', '')[:20].replace('\n', '').replace('\r', '')
    if request.POST.get('api_key', '').strip():          # blank keeps the stored key
        sms.set_api_key(config, request.POST['api_key'].strip()[:300])
    config.enabled = request.POST.get('enabled') == '1'
    config.save()
    audit.warning('server panel: %s saved SMS settings (enabled=%s)', request.user.username, config.enabled)
    messages.success(request, 'تنظیمات پنل پیامک ذخیره شد.')
    return _sms_back()


@policy_required('admin.manage')
@require_POST
def admin_sms_test(request):
    ok, detail = sms.send_sms(request.POST.get('phone', ''), 'پیامک آزمایشی ملک آیدی')
    audit.warning('server panel: %s sent test SMS (ok=%s)', request.user.username, ok)
    (messages.success if ok else messages.error)(request, detail)
    return _sms_back()
