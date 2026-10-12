"""Admin "server" panel: resources, backups, logs, IP blocks, cache and the media file browser.

Admin-only (policy ``admin.manage``). Every mutation is a POST and is written to the
security log with the acting admin.
"""
import ipaddress
from datetime import timedelta
import logging
from io import StringIO
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from main import ipblock, serverops, siteextras, twofactor
from main.access import policy_required
from main.models import BlockedIP, DailyPageView, SiteRedirect, TwoFactorDevice
from main.ratelimit import client_ip

audit = logging.getLogger('django.security.serverpanel')
TABS = ('resources', 'stats', 'database', 'backups', 'logs', 'ips', 'redirects', 'cache', 'security')


def _back(tab, **query):
    url = reverse('main:admin_server')
    return redirect(f'{url}?{urlencode({"tab": tab, **query})}')


def _rel(root, path):
    return '' if path == root else path.relative_to(root).as_posix()


@policy_required('admin.manage')
def admin_server(request):
    tab = request.GET.get('tab') if request.GET.get('tab') in TABS else 'resources'
    ctx = {'tab': tab, 'tabs': TABS}
    if tab == 'resources':
        ctx.update(res=serverops.resources(), folders=serverops.folder_usage(), db_size=serverops.database_size(),
                   last_backup=serverops.last_backup_age_hours(), version=serverops.code_version())
    elif tab == 'stats':
        since = timezone.localdate() - timedelta(days=29)
        views = DailyPageView.objects.filter(day__gte=since)
        ctx.update(days=views.values('day').annotate(total=Sum('views')).order_by('-day'),
                   top_pages=views.values('path').annotate(total=Sum('views')).order_by('-total')[:20],
                   month_total=views.aggregate(total=Sum('views'))['total'] or 0)
    elif tab == 'redirects':
        ctx['redirects'] = SiteRedirect.objects.all()
    elif tab == 'database':
        ctx.update(db=serverops.database_overview())
    elif tab == 'backups':
        ctx['backups'] = serverops.list_backups()
    elif tab == 'logs':
        logs = serverops.list_logs()
        chosen = request.GET.get('file') if request.GET.get('file') in logs else (logs[0] if logs else None)
        ctx.update(logs=logs, chosen=chosen, content=serverops.tail_log(chosen) if chosen else '')
    elif tab == 'ips':
        ctx.update(blocked=BlockedIP.objects.select_related('created_by'), my_ip=client_ip(request))
    elif tab == 'security':
        device = TwoFactorDevice.objects.filter(user=request.user).first()
        ctx['device'] = device
        if device is not None and not device.confirmed:
            ctx['setup_key'] = ' '.join(device.secret[i:i + 4] for i in range(0, len(device.secret), 4))
            ctx['setup_uri'] = twofactor.provisioning_uri(device.secret, request.user.username)
    return render(request, 'main/admin/server.html', ctx)


@policy_required('admin.manage')
@require_POST
def admin_server_backup(request):
    args = ['--media'] if request.POST.get('media') else []
    try:
        call_command('backup_db', *args, stdout=StringIO())
    except CommandError as error:
        messages.error(request, f'پشتیبان‌گیری ناموفق بود: {error}')
    else:
        audit.warning('server panel: backup created by %s', request.user.username)
        messages.success(request, 'نسخه پشتیبان ساخته شد.')
    return _back('backups')


@policy_required('admin.manage')
def admin_server_backup_download(request, name):
    path = serverops.backup_path(name)
    if path is None:
        raise Http404
    audit.warning('server panel: backup %s downloaded by %s', name, request.user.username)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=name)


@policy_required('admin.manage')
@require_POST
def admin_server_backup_delete(request, name):
    path = serverops.backup_path(name)
    if path is None:
        raise Http404
    path.unlink()
    audit.warning('server panel: backup %s deleted by %s', name, request.user.username)
    messages.success(request, 'نسخه پشتیبان حذف شد.')
    return _back('backups')


@policy_required('admin.manage')
@require_POST
def admin_server_ip_block(request):
    raw = request.POST.get('ip', '').strip()
    try:
        ip = str(ipaddress.ip_address(raw))
    except ValueError:
        messages.error(request, 'نشانی IP معتبر نیست.')
        return _back('ips')
    if ip == client_ip(request):
        messages.error(request, 'نشانی IP خودتان را نمی‌توانید مسدود کنید.')
        return _back('ips')
    _, created = BlockedIP.objects.get_or_create(
        ip=ip, defaults={'reason': request.POST.get('reason', '')[:200], 'created_by': request.user})
    ipblock.invalidate()
    if created:
        audit.warning('server panel: %s blocked IP %s', request.user.username, ip)
    messages.success(request, 'نشانی مسدود شد.' if created else 'این نشانی از قبل مسدود بوده است.')
    return _back('ips')


@policy_required('admin.manage')
@require_POST
def admin_server_ip_unblock(request, block_id):
    deleted, _ = BlockedIP.objects.filter(id=block_id).delete()
    ipblock.invalidate()
    if deleted:
        audit.warning('server panel: %s unblocked IP row %s', request.user.username, block_id)
        messages.success(request, 'مسدودیت برداشته شد.')
    return _back('ips')


@policy_required('admin.manage')
@require_POST
def admin_server_db_maintain(request):
    action = request.POST.get('action')
    if action not in ('check', 'optimize'):
        raise Http404
    result = serverops.database_maintain(action)
    audit.warning('server panel: database %s by %s -> %s', action, request.user.username, result)
    if action == 'check':
        (messages.success if result == 'ok' else messages.error)(request, f'نتیجهٔ بررسی سلامت: {result}')
    else:
        messages.success(request, 'آمار جداول به‌روز و پایگاه داده بهینه شد.')
    return _back('database')


@policy_required('admin.manage')
@require_POST
def admin_server_cache_clear(request):
    cache.clear()
    audit.warning('server panel: cache cleared by %s', request.user.username)
    messages.success(request, 'حافظهٔ نهان پاک شد.')
    return _back('cache')


@policy_required('admin.manage')
def admin_server_files(request):
    root_key = request.GET.get('root', 'media')
    rel = request.GET.get('path', '')
    root, directory = serverops.resolve_media(root_key, rel)
    if directory is None or not directory.is_dir():
        if root is not None and directory is None:
            raise Http404
        return render(request, 'main/admin/server_files.html', {'root_key': root_key, 'rows': [], 'rel': '', 'missing': True})
    q = request.GET.get('q', '').strip()
    rows = serverops.search_media(root, directory, q) if q else serverops.list_media(directory)
    base = _rel(root, directory)
    parent = '' if directory == root else _rel(root, directory.parent)
    return render(request, 'main/admin/server_files.html',
                  {'root_key': root_key, 'rows': rows, 'rel': base, 'parent': parent, 'q': q,
                   'roots': list(serverops.media_roots())})


@policy_required('admin.manage')
@require_POST
def admin_server_file_upload(request):
    root_key, rel = request.POST.get('root', ''), request.POST.get('path', '')
    root, directory = serverops.resolve_media(root_key, rel)
    uploaded = request.FILES.get('file')       # extension/size/content already checked by UploadValidationMiddleware
    if directory is None or not directory.is_dir() or uploaded is None:
        raise Http404
    target = directory / get_valid_filename(uploaded.name)
    if target.exists():
        messages.error(request, 'فایلی با همین نام در این پوشه وجود دارد.')
    else:
        with open(target, 'wb') as out:
            for chunk in uploaded.chunks():
                out.write(chunk)
        audit.warning('server panel: %s uploaded %s', request.user.username, target)
        messages.success(request, 'فایل بارگذاری شد.')
    return redirect(f'{reverse("main:admin_server_files")}?{urlencode({"root": root_key, "path": _rel(root, directory)})}')


@policy_required('admin.manage')
def admin_server_file_download(request):
    _, target = serverops.resolve_media(request.GET.get('root', ''), request.GET.get('path', ''))
    if target is None or not target.is_file() or target.is_symlink():
        raise Http404
    audit.warning('server panel: %s downloaded %s', request.user.username, target)
    return FileResponse(open(target, 'rb'), as_attachment=True, filename=target.name)


@policy_required('admin.manage')
@require_POST
def admin_server_file_delete(request):
    root_key, rel = request.POST.get('root', ''), request.POST.get('path', '')
    root, target = serverops.resolve_media(root_key, rel)
    if target is None or not target.is_file() or target.is_symlink():
        raise Http404
    parent = _rel(root, target.parent)
    target.unlink()
    audit.warning('server panel: %s deleted %s', request.user.username, target)
    messages.success(request, 'فایل حذف شد.')
    return redirect(f'{reverse("main:admin_server_files")}?{urlencode({"root": root_key, "path": parent})}')


def _files_url(root_key, rel):
    return f'{reverse("main:admin_server_files")}?{urlencode({"root": root_key, "path": rel})}'


@policy_required('admin.manage')
@require_POST
def admin_server_file_action(request):
    """mkdir / move (rename) / copy / rmdir / zip / unzip inside one media root."""
    op, root_key = request.POST.get('op'), request.POST.get('root', '')
    rel = request.POST.get('path', '')
    root, target = serverops.resolve_media(root_key, rel)
    if target is None or not target.exists() or target.is_symlink():
        raise Http404
    back = _rel(root, target) if op == 'mkdir' or target == root else _rel(root, target.parent)
    try:
        if op == 'mkdir' and target.is_dir():
            serverops.make_folder(target, request.POST.get('name', ''))
            done = 'پوشه ساخته شد.'
        elif op in ('move', 'copy'):
            _, dest = serverops.resolve_media(root_key, request.POST.get('dest', '').strip().strip('/'))
            if dest is None or dest == root:
                raise serverops.FileOpError('مسیر مقصد باید داخل همین پوشهٔ اصلی باشد.')
            if op == 'move':
                serverops.move(root, target, dest)
                done = 'جابه‌جا شد.'
            else:
                serverops.copy(target, dest)
                done = 'کپی شد.'
        elif op == 'rmdir' and target.is_dir():
            serverops.remove_folder(root, target)
            done = 'پوشه حذف شد.'
        elif op == 'zip' and target != root:
            serverops.compress(target)
            done = 'فایل فشرده ساخته شد.'
        elif op == 'unzip' and target.is_file():
            _, extracted, skipped = serverops.extract(target)
            done = f'{extracted} فایل استخراج شد.' + (f' {skipped} فایل با پسوند غیرمجاز یا مسیر ناامن نادیده گرفته شد.' if skipped else '')
        else:
            raise Http404
    except serverops.FileOpError as error:
        messages.error(request, str(error))
    else:
        audit.warning('server panel: %s did %s on %s', request.user.username, op, target)
        messages.success(request, done)
    return redirect(_files_url(root_key, back))


def _clean_redirect(old, new):
    if not old.startswith('/') or old.startswith(siteextras.SKIP_PREFIXES) or old == '/' or '//' in old:
        raise ValueError('نشانی قدیم باید با / شروع شود و نمی‌تواند صفحهٔ اصلی یا بخش مدیریت باشد.')
    if not (new.startswith('/') and not new.startswith('//')) and not new.startswith('https://'):
        raise ValueError('نشانی جدید باید با / یا https:// شروع شود.')
    if old == new:
        raise ValueError('نشانی قدیم و جدید یکسان است.')


@policy_required('admin.manage')
@require_POST
def admin_server_redirect_add(request):
    old, new = request.POST.get('old_path', '').strip(), request.POST.get('new_path', '').strip()
    try:
        _clean_redirect(old, new)
    except ValueError as error:
        messages.error(request, str(error))
        return _back('redirects')
    _, created = SiteRedirect.objects.update_or_create(
        old_path=old[:300], defaults={'new_path': new[:500], 'permanent': request.POST.get('permanent') == '1'})
    siteextras.invalidate()
    audit.warning('server panel: %s set redirect %s -> %s', request.user.username, old, new)
    messages.success(request, 'تغییر مسیر ذخیره شد.' if created else 'تغییر مسیر به‌روز شد.')
    return _back('redirects')


@policy_required('admin.manage')
@require_POST
def admin_server_redirect_delete(request, redirect_id):
    SiteRedirect.objects.filter(id=redirect_id).delete()
    siteextras.invalidate()
    audit.warning('server panel: %s deleted redirect %s', request.user.username, redirect_id)
    messages.success(request, 'تغییر مسیر حذف شد.')
    return _back('redirects')
