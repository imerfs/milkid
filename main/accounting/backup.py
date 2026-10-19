"""Backup and restore of one municipality's accounting data.

A backup is a gzip-compressed JSON file with every accounting row of the municipality (chart of accounts, parties, vouchers,
bills, instalments, contracts, payroll, assets ...). Which tables belong in it is discovered from the models: every model of
the accounting modules that leads, through foreign keys, to its municipality. The audit trail and the backup list are not part
of it; letter links are (a link whose letter was deleted meanwhile is dropped on restore). Scanned documents are included as
records only (the files stay where they are).

Restoring replaces the municipality's accounting data with the backup inside one transaction and takes a safety backup first.
It refuses a backup of another municipality and any row whose id belongs to somebody else, so a wrong or tampered file can
never overwrite another municipality's books.
"""
import gzip
import hashlib
import json
from collections import deque
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.core.management.color import no_style
from django.utils import timezone

from main import audit
from main.accounting import ledger
from main.models import BackupFile, Municipality
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.roles import is_admin

FORMAT, VERSION = 'melkid-accounting-backup', 1
MODULES = {'main.models_accounting', 'main.models_finance', 'main.models_income', 'main.models_payroll', 'main.models_controls',
           'main.models_assets', 'main.models_audit', 'main.models_archive', 'main.models_trade'}
EXCLUDED = {'AuditEvent', 'BackupFile'}
AUTO_KEEP = getattr(settings, 'ACCOUNTING_BACKUP_KEEP', 20)
MAX_UPLOAD = 60 * 1024 * 1024


def _link_fields(model):
    return [f for f in model._meta.concrete_fields if f.is_relation and (f.many_to_one or f.one_to_one)
            and f.related_model._meta.label != settings.AUTH_USER_MODEL]


def _lookup(model, municipality_model):
    """Lookup string that reaches the municipality from ``model`` (``voucher__municipality``), or None."""
    seen, queue = {model}, deque([(model, [])])
    while queue:
        current, path = queue.popleft()
        for field in _link_fields(current):
            if field.related_model is municipality_model:
                return '__'.join(path + [field.name])
        for field in _link_fields(current):
            if field.related_model not in seen:
                seen.add(field.related_model)
                queue.append((field.related_model, path + [field.name]))
    return None


_ORDERED = None


def tables():
    """``[(model, lookup)]`` with parents before children."""
    global _ORDERED
    if _ORDERED is not None:
        return _ORDERED
    municipality_model = apps.get_model('main', 'Municipality')
    chosen = {}
    for model in apps.get_app_config('main').get_models():
        if model.__module__ in MODULES and model.__name__ not in EXCLUDED:
            lookup = _lookup(model, municipality_model)
            if lookup:
                chosen[model] = lookup
    depends = {m: {f.related_model for f in _link_fields(m) if f.related_model in chosen and f.related_model is not m} for m in chosen}
    ordered, remaining = [], dict(depends)
    while remaining:
        ready = sorted((m for m, deps in remaining.items() if not deps - set(ordered)), key=lambda m: m._meta.label)
        if not ready:
            raise RuntimeError('circular foreign keys between accounting tables')
        for model in ready:
            ordered.append(model)
            del remaining[model]
    _ORDERED = [(m, chosen[m]) for m in ordered]
    return _ORDERED


def _scoped(model, lookup, muni):
    return model._base_manager.filter(**{lookup: muni}).order_by('pk')


def snapshot(muni):
    """The backup as a dict (JSON-ready)."""
    out, rows = {}, 0
    for model, lookup in tables():
        objects = json.loads(serializers.serialize('json', _scoped(model, lookup, muni)))
        if objects:
            out[model._meta.label] = objects
            rows += len(objects)
    return {'format': FORMAT, 'version': VERSION, 'municipality': muni.id, 'created': timezone.now().isoformat(), 'rows': rows,
            'tables': out}


def _can_manage(actor):
    return is_admin(actor) or ledger.role_of(actor) == 'dehyari'


def create_for(muni, *, kind='auto', note='', actor=None):
    """Write a backup file for ``muni`` (no permission check: used by the management command and by safety backups)."""
    data = snapshot(muni)
    raw = gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    name = f'muni{muni.id}-{timezone.now():%Y%m%d-%H%M%S}.json.gz'
    backup = BackupFile(municipality=muni, kind=kind, note=note[:200], size=len(raw), rows=data['rows'],
                        sha256=hashlib.sha256(raw).hexdigest(), created_by=actor if actor is not None and actor.pk else None)
    backup.file.save(name, ContentFile(raw), save=True)
    prune(muni)
    return backup


def prune(muni, keep=None):
    """Keep the newest ``keep`` automatic and safety backups; manual ones stay until someone deletes them."""
    keep = AUTO_KEEP if keep is None else keep
    old = list(BackupFile.objects.filter(municipality=muni).exclude(kind='manual').order_by('-id')[keep:])
    for backup in old:
        backup.file.delete(save=False)
        backup.delete()
    return len(old)


def create(actor, *, kind='manual', note=''):
    muni = ledger.municipality_of(actor)
    return create_for(muni, kind=kind, note=note, actor=actor)


def get(actor, backup_id):
    muni = ledger.municipality_of(actor)
    return ledger._own(muni, BackupFile.objects.filter(pk=backup_id).first())


def backups_for(actor):
    return BackupFile.objects.filter(municipality=ledger.municipality_of(actor)).select_related('created_by')


def delete(actor, backup):
    if not _can_manage(actor):
        raise Forbidden('فقط دهیار می‌تواند نسخه پشتیبان را حذف کند.')
    ledger._own(ledger.municipality_of(actor), backup)
    backup.file.delete(save=False)
    backup.delete()


def load(raw):
    """Parse backup bytes (gzip or plain JSON) and check the envelope; returns the dict."""
    if len(raw) > MAX_UPLOAD:
        raise Invalid('فایل بیش از حد بزرگ است.')
    try:
        text = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        data = json.loads(text.decode('utf-8'))
    except Exception:
        raise Invalid('فایل پشتیبان خوانده نشد؛ فایل معتبر نیست.')
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('version') != VERSION or not isinstance(data.get('tables'), dict):
        raise Invalid('این فایل، نسخه پشتیبان حسابداری ملک‌آیدی نیست.')
    known = {m._meta.label for m, _ in tables()}
    if set(data['tables']) - known:
        raise Invalid('فایل شامل جدول ناشناخته است.')
    return data


def _sanitise_users(model, objects, fallback_user):
    """Users may have been deleted since the backup: nullable references become empty, required ones point to the restorer."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user_fields = [f for f in model._meta.concrete_fields if f.is_relation and f.related_model is User]
    if not user_fields:
        return
    wanted = {o['fields'][f.name] for o in objects for f in user_fields if o['fields'].get(f.name)}
    alive = set(User.objects.filter(pk__in=wanted).values_list('pk', flat=True))
    for obj in objects:
        for f in user_fields:
            value = obj['fields'].get(f.name)
            if value and value not in alive:
                obj['fields'][f.name] = None if f.null else fallback_user.pk


def _detach_self_references(model, queryset):
    """A table that points to itself (the chart of accounts: parent) cannot be emptied while rows protect each other."""
    for field in model._meta.concrete_fields:
        if field.is_relation and field.related_model is model and field.null:
            queryset.update(**{field.name: None})


def _drop_orphans(model, objects):
    """Rows that point to a record outside the backup which no longer exists (a deleted letter) cannot be restored."""
    chosen = {m for m, _ in tables()}
    for field in model._meta.concrete_fields:
        if not field.is_relation or field.null or field.related_model in chosen or field.related_model._meta.label == settings.AUTH_USER_MODEL:
            continue
        ids = {o['fields'][field.name] for o in objects if o['fields'].get(field.name)}
        alive = set(field.related_model._base_manager.filter(pk__in=ids).values_list('pk', flat=True))
        objects = [o for o in objects if o['fields'].get(field.name) in alive]
    return objects


def restore(actor, data):
    """Replace the municipality's accounting data with ``data`` (from ``load``). Returns the number of restored rows."""
    if not _can_manage(actor):
        raise Forbidden('فقط دهیار می‌تواند نسخه پشتیبان را بازیابی کند.')
    muni = ledger.municipality_of(actor)
    if data.get('municipality') != muni.id:
        raise Invalid('این نسخه پشتیبان متعلق به دهیاری دیگری است.')
    create_for(muni, kind='before_restore', note='نسخه ایمنی پیش از بازیابی', actor=actor)
    restored = 0
    with transaction.atomic(), audit.muted():
        Municipality.objects.select_for_update().get(pk=muni.pk)
        for model, lookup in reversed(tables()):
            _detach_self_references(model, _scoped(model, lookup, muni))
            _scoped(model, lookup, muni).delete()
        for model, lookup in tables():
            objects = data['tables'].get(model._meta.label, [])
            if not objects:
                continue
            objects = _drop_orphans(model, objects)
            if not objects:
                continue
            direct = next((f for f in model._meta.concrete_fields if f.name == 'municipality'), None)
            if direct is not None and any(o['fields'].get('municipality') != muni.id for o in objects):
                raise Invalid('نسخه پشتیبان شامل ردیف دهیاری دیگری است.')
            pks = [o['pk'] for o in objects]
            if model._base_manager.filter(pk__in=pks).exists():
                raise Conflict('شناسه ردیف‌های نسخه پشتیبان با داده‌ی دهیاری دیگری تداخل دارد؛ بازیابی انجام نشد.')
            _sanitise_users(model, objects, actor)
            for obj in sorted(serializers.deserialize('json', json.dumps(objects), ignorenonexistent=True), key=lambda o: o.object.pk):
                obj.save()
                restored += 1
        statements = connection.ops.sequence_reset_sql(no_style(), [m for m, _ in tables()])
        if statements:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
    audit.record('restore', municipality_id=muni.id, user=actor, summary=f'بازیابی نسخه پشتیبان ({restored} ردیف)')
    return restored
