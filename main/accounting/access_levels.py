"""Configurable access levels of the accounting workspace.

The mayor (or an admin) decides, per area of the workspace, whether the municipality's accountant sees nothing,
only looks, or edits. Mayors and admins always edit everything; without rules everything is ``edit`` (the behaviour
before this feature). Enforcement is in one place: ``guard`` wraps every URL of the accounting URL group, and the
panel checks the level of the tab it is asked to draw.
"""
from functools import wraps

from django.http import HttpResponse, HttpResponseForbidden

from main.models import AccessRule
from main.office.errors import Invalid

ROLE = 'accountant'          # the role these levels apply to
LEVELS = ('none', 'view', 'edit')

# area key, label, workspace tabs that belong to it
AREAS = [
    ('vouchers', 'اسناد حسابداری', ('vouchers', 'statuschange', 'images')),
    ('bills', 'فیش‌های نقدی و پرداخت‌های آنلاین', ('bills', 'online')),
    ('budget', 'بودجه و تامین اعتبار', ('budget', 'credit')),
    ('reports', 'تراز، صورت‌های مالی و گزارش‌ها', ('trial', 'statements', 'reports', 'builder', 'charts')),
    ('contracts', 'قراردادها، ضمانت‌نامه‌ها و اسناد پرداختی', ('contracts', 'guarantees', 'payables')),
    ('income', 'تقسیط، خزانه دریافتی و حمل و نقل', ('plans', 'received', 'transport', 'planimages')),
    ('payroll', 'حقوق و دستمزد', ('pstaff', 'pcalc', 'pattendance', 'pmission', 'pspecialallow', 'pspecialdebt', 'pmisc', 'pworkers',
                                  'peidi', 'prun', 'psettings')),
    ('master', 'طرف‌حساب‌ها، سرفصل‌ها و تنظیمات مالی', ('parties', 'accounts', 'settings')),
    ('assets', 'دارایی‌های ثابت', ('assets',)),
    ('yearend', 'سال مالی، عملیات پایان سال و مغایرت‌گیری', ('setup', 'yearend', 'recon')),
    ('controls', 'قفل تاریخ، کنترل داده و پشتیبان', ('controls', 'backup')),
]
AREA_KEYS = tuple(k for k, _, _ in AREAS)
TAB_AREA = {tab: key for key, _, tabs in AREAS for tab in tabs}
ALWAYS = ('overview', 'tools', 'access', 'audit')          # tabs every accounting user may open (the last two check the role themselves)

# URL name -> area; the first matching prefix wins
_PREFIXES = [
    ('acc_p_voucher', 'vouchers'), ('acc_voucher', 'vouchers'), ('acc_vouchers', 'vouchers'), ('acc_p_status_change', 'vouchers'),
    ('acc_p_image', 'vouchers'), ('acc_p_bill', 'bills'), ('acc_bill', 'bills'), ('acc_payment_cancel', 'bills'),
    ('acc_p_payment', 'bills'), ('acc_p_budget', 'budget'), ('acc_budget', 'budget'), ('acc_p_credit', 'budget'),
    ('acc_p_ledger', 'reports'), ('acc_ledger', 'reports'), ('acc_trial', 'reports'), ('acc_p_report', 'reports'),
    ('acc_p_statement_export', 'reports'), ('acc_p_builder', 'reports'), ('acc_p_chart', 'reports'),
    ('acc_p_print_cheque', 'contracts'), ('acc_p_print_slip', 'income'), ('acc_p_contract', 'contracts'), ('acc_p_statement', 'contracts'), ('acc_p_guarantee', 'contracts'),
    ('acc_p_payable', 'contracts'), ('acc_p_plan', 'income'), ('acc_p_installment', 'income'), ('acc_p_cheque', 'income'),
    ('acc_p_transport', 'income'), ('acc_p_planimage', 'income'),
    ('acc_p_emp', 'payroll'), ('acc_p_debt', 'payroll'), ('acc_p_attendance', 'payroll'), ('acc_p_misc', 'payroll'),
    ('acc_p_mission', 'payroll'), ('acc_p_special', 'payroll'), ('acc_p_run', 'payroll'), ('acc_p_slip', 'payroll'),
    ('acc_p_worker', 'payroll'), ('acc_p_eidi', 'payroll'), ('acc_p_paysettings', 'payroll'), ('acc_p_paytitles', 'payroll'),
    ('acc_p_party', 'master'), ('acc_p_account', 'master'), ('acc_p_setting', 'master'), ('acc_parties', 'master'),
    ('acc_accounts', 'master'), ('acc_p_asset', 'assets'), ('acc_p_seed', 'yearend'), ('acc_seed', 'yearend'),
    ('acc_p_year', 'yearend'), ('acc_p_yearend', 'yearend'), ('acc_home', 'yearend'), ('acc_p_recon', 'yearend'),
    ('acc_p_lock', 'controls'), ('acc_p_integrity', 'controls'), ('acc_p_backup', 'controls'), ('acc_p_letter', 'vouchers'),
]
# Names that are not an area at all: the tab dispatcher (checks the tab itself) and the pages the role checks itself
EXEMPT = ('acc_panel', 'acc_p_search', 'acc_p_access_save', 'acc_p_audit_export', 'acc_p_calculator',
          'acc_p_shortcuts', 'acc_p_tools_words', 'acc_p_tools_date', 'acc_p_tools_loan')


def area_of(name):
    """The area a URL name belongs to, ``None`` for the exempt ones; raises KeyError for a name nobody mapped."""
    if name in EXEMPT:
        return None
    for prefix, area in _PREFIXES:
        if name == prefix or name.startswith(prefix):
            return area
    raise KeyError(name)


def rules_for(muni):
    """{area: level} for the municipality's accountant (missing areas are ``edit``)."""
    levels = {key: 'edit' for key in AREA_KEYS}
    for rule in AccessRule.objects.filter(municipality=muni, role=ROLE):
        if rule.area in levels:
            levels[rule.area] = rule.level
    return levels


def level_for(user, area):
    """'none' / 'view' / 'edit' for ``user`` in ``area``. Only the accountant role is restricted."""
    from main.accounting import ledger
    if area is None or ledger.role_of(user) != ROLE or user.is_superuser:
        return 'edit'
    try:
        muni = ledger.municipality_of(user)
    except Exception:                       # no municipality: the view itself answers 404
        return 'edit'
    return rules_for(muni).get(area, 'edit')


def tab_level(user, tab):
    area = TAB_AREA.get(tab)
    return 'edit' if area is None else level_for(user, area)


def hidden_tabs(user):
    """Tabs the user may not open at all (for the menu)."""
    from main.accounting import ledger
    if ledger.role_of(user) != ROLE or user.is_superuser:
        return []
    return [tab for tab, area in TAB_AREA.items() if level_for(user, area) == 'none']


def save_rules(actor, levels):
    """Replace the accountant's levels. ``levels`` maps area key to a level; unknown keys/levels are refused."""
    from main.accounting import ledger
    from main.office.errors import Forbidden
    from main.office.roles import is_admin
    muni = ledger.municipality_of(actor)
    if not is_admin(actor) and ledger.role_of(actor) != 'dehyari':
        raise Forbidden('فقط دهیار می‌تواند سطوح دسترسی را تغییر دهد.')
    for area, level in levels.items():
        if area not in AREA_KEYS or level not in LEVELS:
            raise Invalid('سطح دسترسی نامعتبر است.')
    for area, level in levels.items():
        if level == 'edit':
            AccessRule.objects.filter(municipality=muni, role=ROLE, area=area).delete()
        else:
            AccessRule.objects.update_or_create(municipality=muni, role=ROLE, area=area, defaults={'level': level})
    return rules_for(muni)


def _denied(request, message):
    if request.headers.get('HX-Request'):
        import json
        response = HttpResponse(status=403)
        response['HX-Trigger'] = json.dumps({'accError': {'message': message}})
        return response
    return HttpResponseForbidden(message)


def guard(patterns):
    """Wrap every URL of the accounting group so the accountant's level for its area is enforced."""
    from django.urls import path
    out = []
    for p in patterns:
        area = area_of(p.name)
        if area is None:
            out.append(p)
            continue
        view = p.callback

        @wraps(view)
        def wrapped(request, *args, _view=view, _area=area, **kwargs):
            if request.user.is_authenticated:
                level = level_for(request.user, _area)
                needed = 'view' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'edit'
                if level == 'none' or (needed == 'edit' and level != 'edit'):
                    return _denied(request, 'مدیر دهیاری این بخش را برای شما ' + ('بسته است.' if level == 'none' else 'فقط‌خواندنی کرده است.'))
            return _view(request, *args, **kwargs)

        out.append(path(str(p.pattern), wrapped, name=p.name))
    return out
