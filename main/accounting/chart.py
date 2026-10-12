"""Default chart of accounts, taken from the reference software (see docs/accounting-spec.md). Idempotent."""
from django.db import transaction

from main.accounting.ledger import municipality_of
from main.models import Account, CostCenter

# code, title, kind, nature, postable, requires_party, parent code
CHART = [
    ('111', 'افتتاحیه', 'asset', 'debit', True, False, None),
    ('112', 'بانک‌ها', 'asset', 'debit', False, False, None),
    ('1120101', 'بانک ملی', 'asset', 'debit', True, False, '112'),
    ('1120201', 'بانک کشاورزی', 'asset', 'debit', True, False, '112'),
    ('113', 'بدهکاران', 'asset', 'debit', True, True, None),
    ('114', 'علی‌الحساب‌ها', 'asset', 'debit', True, True, None),
    ('116', 'اسناد دریافتنی', 'asset', 'debit', True, True, None),
    ('118', 'سایر حساب‌ها و اسناد دریافتنی', 'asset', 'debit', True, False, None),
    ('311', 'بستانکاران', 'liability', 'credit', True, True, None),
    ('312', 'بیمه پرداختنی', 'liability', 'credit', True, False, None),
    ('313', 'مالیات پرداختنی', 'liability', 'credit', True, False, None),
    ('314', 'سپرده‌های پرداختنی', 'liability', 'credit', True, True, None),
    ('315', 'بستانکاران کارکنان', 'liability', 'credit', True, True, None),
    ('318', 'سایر حساب‌ها و اسناد پرداختنی', 'liability', 'credit', True, False, None),
    ('410', 'مازاد / کسری', 'equity', 'credit', True, False, None),
    ('411', 'اختتامیه', 'closing', 'credit', True, False, None),
    ('501', 'منابع درآمدی', 'budget_resource', 'credit', False, False, None),
    ('5010101001', 'عوارض بر کالا و خدمات', 'budget_resource', 'credit', True, False, '501'),
    ('5010101007', 'کمک از محل موضوع', 'budget_resource', 'credit', True, False, '501'),
    ('502', 'منابع حاصل از واگذاری دارایی‌های سرمایه‌ای', 'budget_resource', 'credit', False, False, None),
    ('503', 'منابع حاصل از واگذاری دارایی‌های مالی', 'budget_resource', 'credit', False, False, None),
    ('601', 'مصارف هزینه‌ای', 'budget_use', 'debit', False, False, None),
    ('6010101001', 'حقوق دهیار', 'budget_use', 'debit', True, False, '601'),
    ('6010102001', 'مزایای دهیار', 'budget_use', 'debit', True, False, '601'),
    ('602', 'تملک دارایی‌های سرمایه‌ای', 'budget_use', 'debit', False, False, None),
    ('603', 'تملک دارایی‌های مالی', 'budget_use', 'debit', False, False, None),
]
COST_CENTERS = [('1', 'امور مالی'), ('2', 'امور اداری')]


def seed_default_accounts(actor):
    muni = municipality_of(actor)
    with transaction.atomic():
        made = {}
        for code, title, kind, nature, postable, party, parent in CHART:
            made[code], _ = Account.objects.get_or_create(
                municipality=muni, code=code,
                defaults=dict(title=title, kind=kind, nature=nature, is_postable=postable,
                              requires_party=party, parent=made.get(parent)))
        for code, title in COST_CENTERS:
            CostCenter.objects.get_or_create(municipality=muni, code=code, defaults={'title': title})
    return len(made)
