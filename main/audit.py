"""Audit trail of the accounting workspace: who created, changed or deleted which record, and who signed in or out.

``AuditMiddleware`` remembers the acting user and address for the duration of a request; Django signals on the audited
models and on sign-in/out write ``AuditEvent`` rows. Nothing here can fail a request: recording errors are swallowed
and logged, because an audit gap is better than a broken payment.
"""
import contextvars
import logging

from django.apps import apps
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save

logger = logging.getLogger(__name__)
_current = contextvars.ContextVar('audit_actor', default=None)

# Models whose changes are recorded (accounting, income, finance and payroll data, plus the controls themselves)
AUDITED = ('FiscalYear', 'Account', 'Party', 'CostCenter', 'Voucher', 'BudgetLine', 'Bill', 'BillPayment', 'CreditProvision',
           'Contract', 'ContractStatement', 'Guarantee', 'PayableDocument', 'InstallmentPlan', 'Installment', 'TransportIncome',
           'Employee', 'EmployeeDebt', 'PayrollRun', 'DailyWorker', 'PayrollSettings', 'AccountingLock', 'AccessRule', 'Asset')
SKIP_FIELDS = {'updated_at', 'set_at', 'modified_at'}
MAX_VALUE = 120


class AuditMiddleware:
    """Remember who is acting, so signals (which only see the model) can say who changed what."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current.set({'request': request})
        try:
            return self.get_response(request)
        finally:
            _current.reset(token)


def _actor():
    state = _current.get()
    request = state['request'] if state else None
    user = getattr(request, 'user', None) if request is not None else None
    if user is None or not getattr(user, 'is_authenticated', False):
        user = None
    ip = None
    if request is not None:
        ip = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR') or None
    return user, ip


def _municipality_id(instance):
    for path in ('municipality_id', 'fiscal_year.municipality_id', 'bill.municipality_id', 'plan.municipality_id',
                 'contract.municipality_id', 'employee.municipality_id', 'voucher.municipality_id'):
        node = instance
        try:
            for part in path.split('.'):
                node = getattr(node, part)
        except Exception:                                # a missing relation just means "try the next path"
            continue
        if node:
            return node
    return None


def _label(instance):
    try:
        return str(instance)[:200]
    except Exception:
        return f'{type(instance).__name__} {instance.pk}'


def _short(value):
    text = '' if value is None else str(value)
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE] + '…'


def record(action, *, instance=None, user=None, username='', summary='', changes=None, municipality_id=None, ip=None):
    """Write one event; never raises."""
    from main.models import AuditEvent
    try:
        if user is None and not username:
            user, ip_seen = _actor()
            ip = ip or ip_seen
        AuditEvent.objects.create(
            municipality_id=municipality_id if municipality_id is not None else (_municipality_id(instance) if instance is not None else None),
            user=user if user is not None and getattr(user, 'pk', None) else None,
            username=(username or (user.get_username() if user is not None else ''))[:150], action=action,
            model=type(instance).__name__ if instance is not None else '', object_id=str(instance.pk) if instance is not None else '',
            summary=(summary or (_label(instance) if instance is not None else ''))[:300], changes=changes or {}, ip=ip)
    except Exception:
        logger.exception('audit record failed')


def _before_save(sender, instance, **kwargs):
    """Remember the stored values so ``_after_save`` can say what changed."""
    instance._audit_old = None
    if instance.pk is None or kwargs.get('raw'):
        return
    try:
        instance._audit_old = sender._base_manager.filter(pk=instance.pk).values().first()
    except Exception:
        instance._audit_old = None


def _after_save(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    changes = {}
    old = getattr(instance, '_audit_old', None)
    if not created and old:
        for field in sender._meta.concrete_fields:
            if field.name in SKIP_FIELDS:
                continue
            before, after = old.get(field.attname), getattr(instance, field.attname)
            if before != after:
                changes[field.name] = [_short(before), _short(after)]
        if not changes:
            return
    record('create' if created else 'update', instance=instance, changes=changes)


def _after_delete(sender, instance, **kwargs):
    record('delete', instance=instance)


def _login(sender, request, user, **kwargs):
    from main.accounting.ledger import municipality_of
    try:
        muni_id = municipality_of(user).id
    except Exception:
        muni_id = None
    record('login', user=user, municipality_id=muni_id, summary='ورود به سامانه',
           ip=(request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')) if request is not None else None)


def _logout(sender, request, user, **kwargs):
    if user is not None:
        record('logout', user=user, summary='خروج از سامانه',
               ip=(request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')) if request is not None else None)


def _login_failed(sender, credentials, request=None, **kwargs):
    record('login_failed', username=str(credentials.get('username', ''))[:150], summary='ورود ناموفق',
           ip=(request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')) if request is not None else None)


def connect():
    """Connect the signals (called from ``MainConfig.ready``)."""
    for name in AUDITED:
        try:
            model = apps.get_model('main', name)
        except LookupError:
            continue
        uid = f'audit-{name}'
        pre_save.connect(_before_save, sender=model, dispatch_uid=f'{uid}-pre')
        post_save.connect(_after_save, sender=model, dispatch_uid=f'{uid}-post')
        post_delete.connect(_after_delete, sender=model, dispatch_uid=f'{uid}-del')
    user_logged_in.connect(_login, dispatch_uid='audit-login')
    user_logged_out.connect(_logout, dispatch_uid='audit-logout')
    user_login_failed.connect(_login_failed, dispatch_uid='audit-login-failed')
