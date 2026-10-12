"""Admin "server" panel: resources, backups, logs, IP blocks, cache and the media file browser.

Admin-only (policy ``admin.manage``). Every mutation is a POST and is written to the
security log with the acting admin.
"""
import ipaddress
import logging
from io import StringIO
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_POST

from main import ipblock, serverops
from main.access import policy_required
from main.models import BlockedIP
from main.ratelimit import client_ip

audit = logging.getLogger('django.security.serverpanel')
TABS = ('resources', 'database', 'backups', 'logs', 'ips', 'cache')


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
                   last_backup=serverops.last_backup_age_hours())
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
