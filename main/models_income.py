"""Income-side models of the accountant workspace: instalment plans with their schedule, people and cheques, plus
transport income. Imported at the end of main/models.py. Money is whole rials; every row belongs to one Municipality.
Rules live in main/accounting/instalments.py and main/accounting/transport.py.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from main.models_accounting import MONEY


class InstallmentPlan(models.Model):
    """تقسیط: a debt split into dated instalments (what is owed minus the cash paid up front)."""
    STATUSES = [('active', 'در جریان'), ('settled', 'تسویه‌شده'), ('canceled', 'فسخ‌شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='installment_plans')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='installment_plans')
    number = models.PositiveIntegerField(verbose_name='شماره تقسیط')   # restarts every fiscal year
    date = models.DateField(verbose_name='تاریخ')
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='installment_plans', verbose_name='مودی')
    property_file = models.CharField(max_length=40, blank=True, verbose_name='شماره پرونده')
    renovation_code = models.CharField(max_length=40, blank=True, verbose_name='کد نوسازی')
    plot_no = models.CharField(max_length=40, blank=True, verbose_name='پلاک ثبتی')
    address = models.CharField(max_length=500, blank=True, verbose_name='آدرس')
    letter_no = models.CharField(max_length=40, blank=True, verbose_name='شماره نامه')
    letter_date = models.DateField(null=True, blank=True, verbose_name='تاریخ نامه')
    request_no = models.CharField(max_length=40, blank=True, verbose_name='شماره درخواست')
    total_debt = models.DecimalField(verbose_name='کل بدهی', **MONEY)
    cash_paid = models.DecimalField(default=0, verbose_name='پرداخت نقدی', **MONEY)
    plan_amount = models.DecimalField(verbose_name='مبلغ تقسیط', **MONEY)   # total_debt - cash_paid
    count = models.PositiveSmallIntegerField(verbose_name='تعداد اقساط')
    status = models.CharField(max_length=10, choices=STATUSES, default='active', verbose_name='وضعیت')
    canceled_on = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=500, blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'پرونده تقسیط'
        verbose_name_plural = 'پرونده‌های تقسیط'
        ordering = ['fiscal_year', 'number']
        constraints = [
            models.UniqueConstraint(fields=['fiscal_year', 'number'], name='uniq_plan_number'),
            models.CheckConstraint(condition=Q(plan_amount__gt=0), name='plan_amount_positive'),
            models.CheckConstraint(condition=Q(count__gte=1), name='plan_count_positive'),
        ]


class Installment(models.Model):
    """One instalment. A cheque/note only counts as paid once the treasury confirms it was collected."""
    METHODS = [('cash', 'نقدی'), ('transfer', 'واریز به حساب'), ('card', 'کارتخوان'), ('online', 'الکترونیکی'),
               ('cheque', 'چک'), ('promissory', 'سفته')]
    POSITIONS = [('office', 'نزد دهیاری'), ('treasury', 'ارسال شده به خزانه'), ('collected', 'وصول شد'),
                 ('bounced', 'برگشت خورد')]

    plan = models.ForeignKey(InstallmentPlan, on_delete=models.CASCADE, related_name='installments')
    seq = models.PositiveSmallIntegerField(verbose_name='ردیف')
    due_date = models.DateField(verbose_name='موعد پرداخت')
    amount = models.DecimalField(verbose_name='مبلغ قسط', **MONEY)
    paid_amount = models.DecimalField(default=0, verbose_name='پرداخت‌شده', **MONEY)
    paid_on = models.DateField(null=True, blank=True)
    method = models.CharField(max_length=12, choices=METHODS, blank=True, verbose_name='روش پرداخت')
    # cheque / note details (only when method is cheque or promissory)
    series = models.CharField(max_length=40, blank=True, verbose_name='سری / صیاد')
    serial = models.CharField(max_length=40, blank=True, verbose_name='سریال')
    bank = models.CharField(max_length=100, blank=True, verbose_name='بانک')
    account_no = models.CharField(max_length=40, blank=True, verbose_name='شماره حساب')
    owner_name = models.CharField(max_length=150, blank=True, verbose_name='صاحب حساب')
    owner_national_id = models.CharField(max_length=11, blank=True, verbose_name='کد ملی صاحب حساب')
    cheque_date = models.DateField(null=True, blank=True, verbose_name='تاریخ چک')
    position = models.CharField(max_length=10, choices=POSITIONS, blank=True, verbose_name='موقعیت')

    class Meta:
        verbose_name = 'قسط'
        verbose_name_plural = 'اقساط'
        ordering = ['plan', 'seq']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'seq'], name='uniq_installment_seq'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='installment_amount_positive'),
            models.CheckConstraint(condition=Q(paid_amount__gte=0) & Q(paid_amount__lte=models.F('amount')),
                                   name='installment_paid_within_amount'),
        ]

    @property
    def remaining(self):
        return self.amount - self.paid_amount

    @property
    def is_cheque(self):
        return self.method in ('cheque', 'promissory')


class InstallmentEvent(models.Model):
    """History of a received cheque/note: where it moved, when, and who did it."""
    installment = models.ForeignKey(Installment, on_delete=models.CASCADE, related_name='events')
    position = models.CharField(max_length=10, choices=Installment.POSITIONS)
    date = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class InstallmentPerson(models.Model):
    """اطلاعات افراد: other people tied to a plan (guarantors, co-owners, heirs...)."""
    RELATIONS = [('owner', 'مالک'), ('guarantor', 'ضامن'), ('heir', 'وارث'), ('representative', 'نماینده'),
                 ('other', 'سایر')]
    plan = models.ForeignKey(InstallmentPlan, on_delete=models.CASCADE, related_name='people')
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='+')
    relation = models.CharField(max_length=15, choices=RELATIONS, default='guarantor')

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['plan', 'party', 'relation'], name='uniq_plan_person')]


class TransportIncome(models.Model):
    """درآمد حمل و نقل: a fee collected for a vehicle or transport service."""
    STATUSES = [('received', 'دریافت‌شده'), ('canceled', 'ابطال‌شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='transport_incomes')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='transport_incomes')
    number = models.PositiveIntegerField(verbose_name='شماره')   # restarts every fiscal year
    date = models.DateField(verbose_name='تاریخ')
    plate = models.CharField(max_length=20, verbose_name='پلاک خودرو')
    service = models.CharField(max_length=100, verbose_name='نوع خدمت')
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                              verbose_name='پرداخت‌کننده')
    amount = models.DecimalField(verbose_name='مبلغ', **MONEY)
    receipt_no = models.CharField(max_length=40, blank=True, verbose_name='شماره رسید')
    description = models.CharField(max_length=300, blank=True, verbose_name='توضیحات')
    status = models.CharField(max_length=10, choices=STATUSES, default='received')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'درآمد حمل و نقل'
        verbose_name_plural = 'درآمدهای حمل و نقل'
        ordering = ['fiscal_year', 'number']
        constraints = [
            models.UniqueConstraint(fields=['fiscal_year', 'number'], name='uniq_transport_number'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='transport_amount_positive'),
        ]
