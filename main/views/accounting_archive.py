"""Backups and letters linked to accounting records. Rules live in main/accounting/backup and letter_links."""
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from main.accounting import access_levels, backup, ledger, letter_links
from main.models import Contract, InstallmentPlan, Voucher
from main.office.errors import Invalid, OfficeError
from main.office.roles import is_admin
from main.views.accounting_panel import PANEL, _done, _failed
from main.views.accounting_views import _guard

CONFIRM_WORD = 'بازیابی'


def _mayor(user):
    return is_admin(user) or ledger.role_of(user) == 'dehyari'


def tab_backup(request, year, ctx):
    ctx.update(backups=backup.backups_for(request.user), can_restore=_mayor(request.user), confirm_word=CONFIRM_WORD,
               backup_keep=backup.AUTO_KEEP)


@_guard()
@require_POST
def acc_p_backup_create(request):
    try:
        item = backup.create(request.user, kind='manual', note=request.POST.get('note', ''))
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'نسخه پشتیبان ساخته شد ({item.rows} ردیف).')


@_guard()
def acc_p_backup_download(request, backup_id):
    item = backup.get(request.user, backup_id)
    try:
        handle = item.file.open('rb')
    except FileNotFoundError:
        raise Http404()
    response = FileResponse(handle, content_type='application/gzip')
    response['Content-Disposition'] = f'attachment; filename="{item.file.name.rsplit("/", 1)[-1]}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@_guard()
@require_POST
def acc_p_backup_delete(request, backup_id):
    try:
        backup.delete(request.user, backup.get(request.user, backup_id))
    except OfficeError as exc:
        return _failed(exc)
    return _done('نسخه پشتیبان حذف شد.')


@_guard()
@require_POST
def acc_p_backup_restore(request):
    """Restore from a stored backup (``backup_id``) or an uploaded file (``file``); the typed word guards against a slip."""
    try:
        if request.POST.get('confirm', '').strip() != CONFIRM_WORD:
            raise Invalid(f'برای بازیابی، کلمه «{CONFIRM_WORD}» را در کادر تایید بنویسید.')
        if request.FILES.get('file'):
            upload = request.FILES['file']
            if upload.size > backup.MAX_UPLOAD:
                raise Invalid('فایل بیش از حد بزرگ است.')
            data = backup.load(upload.read())
        else:
            stored = backup.get(request.user, request.POST.get('backup_id') or 0)
            with stored.file.open('rb') as handle:
                data = backup.load(handle.read())
        count = backup.restore(request.user, data)
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'بازیابی انجام شد؛ {count} ردیف جایگزین شد. نسخه ایمنی پیش از آن ساخته شده است.')


# ---------- letters linked to records ----------

TARGETS = {'voucher': (Voucher, 'vouchers'), 'contract': (Contract, 'contracts'), 'plan': (InstallmentPlan, 'income')}


def _target(request, kind, pk):
    if kind not in TARGETS:
        raise Http404()
    model, area = TARGETS[kind]
    muni = ledger.municipality_of(request.user)
    obj = model.objects.filter(pk=pk).first()
    owner = getattr(obj, 'municipality_id', None) if obj is not None else None
    if obj is None or owner != muni.id or (kind == 'voucher' and obj.deleted_at is not None):
        raise Http404()
    return obj, area


def _links_response(request, kind, obj):
    return render(request, PANEL + '_letter_links.html', {
        'kind': kind, 'obj': obj, 'links': letter_links.links_for(request.user, **{kind: obj}),
        'letters': letter_links.choices(request.user)})


@_guard()
def acc_p_letter_links(request, kind, pk):
    obj, area = _target(request, kind, pk)
    if access_levels.level_for(request.user, area) == 'none':
        raise Http404()
    return _links_response(request, kind, obj)


@_guard()
@require_POST
def acc_p_letter_link(request, kind, pk):
    obj, area = _target(request, kind, pk)
    if access_levels.level_for(request.user, area) != 'edit':
        return HttpResponse(status=403)
    try:
        letter_links.link(request.user, int(request.POST.get('letter') or 0), **{kind: obj})
    except OfficeError as exc:
        return _failed(exc)
    return _links_response(request, kind, obj)


@_guard()
@require_POST
def acc_p_letter_unlink(request, link_id):
    try:
        row = letter_links.LetterLink.objects.filter(pk=link_id).first()
        if row is None:
            raise Http404()
        kind = 'voucher' if row.voucher_id else 'contract' if row.contract_id else 'plan'
        if access_levels.level_for(request.user, TARGETS[kind][1]) != 'edit':
            return HttpResponse(status=403)
        obj = getattr(row, kind)
        letter_links.unlink(request.user, link_id)
    except OfficeError as exc:
        return _failed(exc)
    return _links_response(request, kind, obj)


BUILDERS = {'backup': tab_backup}
