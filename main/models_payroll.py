"""Payroll models (حقوق و دستمزد) of the accountant workspace. Imported at the end of main/models.py.

Money is whole rials; rates are decimals. Every row belongs to one Municipality. Payroll periods are Jalali (year, month).
Rules live in main/accounting/payroll.py; the numbers that depend on law (insurance %, overtime multiplier...) are stored
per municipality in PayrollSettings so they can be changed without code.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from main.models_accounting import MONEY

CALC_GROUPS = [('retired', 'بازنشستگان'), ('official_worker', 'کارگر رسمی'), ('contract_worker', 'کارگر قراردادی'),
               ('ss_employee', 'کارمند تامین اجتماعی'), ('medical_employee', 'کارمند تامین درمانی')]
LIST_TITLES = ['کارکنان رسمی و پیمانی', 'کارکنان اداری', 'کارمندان قراردادی', 'کارگران قراردادی', 'کارگران رسمی',
               'کارگران خدماتی و عمرانی', 'شهردار', 'دهیار']
MONTHS = [(i, n) for i, n in enumerate(['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر',
                                        'دی', 'بهمن', 'اسفند'], start=1)]
RATE = {'max_digits': 7, 'decimal_places': 2}


class PayrollSettings(models.Model):
    """Rates used by the monthly calculation. Defaults are common Iranian values; a municipality may change them."""
    municipality = models.OneToOneField('main.Municipality', on_delete=models.CASCADE, related_name='payroll_settings')
    month_days = models.PositiveSmallIntegerField(default=30, verbose_name='روزهای ماه برای محاسبه')
    hours_per_day = models.DecimalField(default=7.33, verbose_name='ساعت کار روزانه', **RATE)
    overtime_multiplier = models.DecimalField(default=1.4, verbose_name='ضریب اضافه کار', **RATE)
    holiday_multiplier = models.DecimalField(default=1.4, verbose_name='ضریب جمعه‌کاری و تعطیل', **RATE)
    night_pct = models.DecimalField(default=35, verbose_name='٪ شب کاری', **RATE)
    insurance_employee_pct = models.DecimalField(default=7, verbose_name='٪ بیمه سهم فرد', **RATE)
    insurance_employer_pct = models.DecimalField(default=20, verbose_name='٪ بیمه سهم کارفرما', **RATE)
    unemployment_pct = models.DecimalField(default=3, verbose_name='٪ بیمه بیکاری (کارفرما)', **RATE)
    insurance_ceiling = models.DecimalField(default=0, verbose_name='سقف ماهانه مشمول بیمه (۰ = بدون سقف)', **MONEY)
    min_daily_wage = models.DecimalField(default=0, verbose_name='حداقل دستمزد روزانه', **MONEY)

    class Meta:
        verbose_name = 'تنظیمات حقوق'
        verbose_name_plural = 'تنظیمات حقوق'


class AllowanceTitle(models.Model):
    """Title of allowance slot 1..40 (the slots are fixed, the names are the municipality's)."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='allowance_titles')
    slot = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=100)

    class Meta:
        ordering = ['slot']
        constraints = [models.UniqueConstraint(fields=['municipality', 'slot'], name='uniq_allowance_slot'),
                       models.CheckConstraint(condition=Q(slot__gte=1, slot__lte=40), name='allowance_slot_range')]


class Employee(models.Model):
    GENDERS = [('m', 'مرد'), ('f', 'زن')]
    MARITAL = [('single', 'مجرد'), ('married', 'متاهل')]
    INSURANCES = [('social', 'تامین اجتماعی'), ('medical', 'تامین درمانی'), ('none', 'بدون بیمه')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='employees')
    code = models.PositiveIntegerField(verbose_name='شماره شناسایی')   # per municipality
    first_name = models.CharField(max_length=100, verbose_name='نام')
    last_name = models.CharField(max_length=100, verbose_name='نام خانوادگی')
    father_name = models.CharField(max_length=100, blank=True, verbose_name='نام پدر')
    id_card_no = models.CharField(max_length=20, blank=True, verbose_name='شماره شناسنامه')
    birth_date = models.DateField(null=True, blank=True, verbose_name='تاریخ تولد')
    marital = models.CharField(max_length=10, choices=MARITAL, default='single', verbose_name='تاهل')
    children = models.PositiveSmallIntegerField(default=0, verbose_name='تعداد اولاد')
    gender = models.CharField(max_length=1, choices=GENDERS, default='m', verbose_name='جنسیت')
    veteran_status = models.CharField(max_length=50, default='عادی', verbose_name='وضعیت ایثارگری')
    national_id = models.CharField(max_length=10, verbose_name='شماره ملی')
    service_status = models.CharField(max_length=50, blank=True, verbose_name='وضعیت خدمتی')
    calc_group = models.CharField(max_length=20, choices=CALC_GROUPS, verbose_name='گروه محاسباتی')
    org_status = models.CharField(max_length=50, blank=True, verbose_name='وضعیت سازمانی')
    employment_type = models.CharField(max_length=50, blank=True, verbose_name='نوع استخدام')
    list_title = models.CharField(max_length=60, verbose_name='عنوان لیست')
    post_level = models.CharField(max_length=50, blank=True, verbose_name='سطح پست')
    job_rank = models.CharField(max_length=50, blank=True, verbose_name='رتبه شغلی')
    education = models.CharField(max_length=50, blank=True, verbose_name='مدرک تحصیلی')
    start_date = models.DateField(verbose_name='تاریخ شروع خدمت')
    end_date = models.DateField(null=True, blank=True, verbose_name='تاریخ پایان خدمت')
    org_unit = models.CharField(max_length=100, blank=True, verbose_name='واحد سازمانی')
    cost_center = models.ForeignKey('main.CostCenter', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                    verbose_name='مرکز هزینه')
    job_title = models.CharField(max_length=100, verbose_name='عنوان شغل')
    insurance_type = models.CharField(max_length=10, choices=INSURANCES, default='social', verbose_name='نوع بیمه')
    insurance_no = models.CharField(max_length=20, blank=True, verbose_name='شماره بیمه‌گری')
    ins_main = models.PositiveSmallIntegerField(default=1, verbose_name='بیمه عادی: اصلی')
    ins_dep1 = models.PositiveSmallIntegerField(default=0, verbose_name='بیمه عادی: تبعی یک')
    ins_dep2 = models.PositiveSmallIntegerField(default=0, verbose_name='بیمه عادی: تبعی دو')
    ins_dep3 = models.PositiveSmallIntegerField(default=0, verbose_name='بیمه عادی: تبعی سه')
    supp_normal = models.PositiveSmallIntegerField(default=0, verbose_name='تکمیلی: عادی')
    supp_special1 = models.PositiveSmallIntegerField(default=0, verbose_name='تکمیلی: خاص یک (زیر ۶۰)')
    supp_special2 = models.PositiveSmallIntegerField(default=0, verbose_name='تکمیلی: خاص دو (۶۰ تا ۷۰)')
    supp_special3 = models.PositiveSmallIntegerField(default=0, verbose_name='تکمیلی: خاص سه (بالای ۷۰)')
    bank_name = models.CharField(max_length=60, blank=True, verbose_name='نام بانک')
    account_type = models.CharField(max_length=40, blank=True, verbose_name='نوع حساب')
    account_main = models.CharField(max_length=40, blank=True, verbose_name='شماره حساب اصلی')
    account_misc = models.CharField(max_length=40, blank=True, verbose_name='شماره حساب متفرقه')
    active = models.BooleanField(default=True, verbose_name='فعال')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        verbose_name = 'پرسنل'
        verbose_name_plural = 'پرسنل'
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['municipality', 'code'], name='uniq_employee_code'),
                       models.UniqueConstraint(fields=['municipality', 'national_id'], name='uniq_employee_national_id')]

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()


class EmployeeAllowance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='allowances')
    slot = models.PositiveSmallIntegerField()
    amount = models.DecimalField(**MONEY)

    class Meta:
        ordering = ['employee', 'slot']
        constraints = [models.UniqueConstraint(fields=['employee', 'slot'], name='uniq_employee_slot'),
                       models.CheckConstraint(condition=Q(slot__gte=1, slot__lte=40), name='emp_allowance_slot_range'),
                       models.CheckConstraint(condition=Q(amount__gte=0), name='emp_allowance_not_negative')]


class EmployeeDebt(models.Model):
    """بدهی / وام: deducted every month (the personal share) until paid off; the organisation share is its own cost."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='debts')
    title = models.CharField(max_length=100, verbose_name='عنوان بدهی')
    total = models.DecimalField(verbose_name='کل بدهی', **MONEY)
    installment = models.DecimalField(verbose_name='سهم فرد (قسط)', **MONEY)
    org_share = models.DecimalField(default=0, verbose_name='سهم سازمان', **MONEY)
    paid = models.DecimalField(default=0, verbose_name='پرداخت‌شده', **MONEY)
    start_year = models.PositiveSmallIntegerField(verbose_name='سال شروع')
    start_month = models.PositiveSmallIntegerField(verbose_name='ماه شروع')
    active = models.BooleanField(default=True, verbose_name='فعال')
    note = models.CharField(max_length=300, blank=True, verbose_name='توضیحات')

    class Meta:
        ordering = ['employee', 'id']
        constraints = [
            models.CheckConstraint(condition=Q(total__gt=0) & Q(installment__gt=0), name='debt_amounts_positive'),
            models.CheckConstraint(condition=Q(paid__gte=0) & Q(paid__lte=models.F('total')), name='debt_paid_within_total'),
            models.CheckConstraint(condition=Q(start_month__gte=1, start_month__lte=12), name='debt_month_range')]

    @property
    def remaining(self):
        return self.total - self.paid


class PersonalCalc(models.Model):
    """نحوه محاسبات فردی: personal rates and percentages that override the municipality's defaults (0 = use default)."""
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='calc')
    mission_day_rate = models.DecimalField(default=0, verbose_name='یک روز ماموریت', **MONEY)
    overtime_rate = models.DecimalField(default=0, verbose_name='یک ساعت اضافه کار عادی', **MONEY)
    holiday_overtime_rate = models.DecimalField(default=0, verbose_name='یک ساعت اضافه کار تعطیل', **MONEY)
    min_daily_wage = models.DecimalField(default=0, verbose_name='حداقل دستمزد روزانه', **MONEY)
    insurance_employee_pct = models.DecimalField(default=0, verbose_name='٪ بیمه سهم فرد', **RATE)
    insurance_employer_pct = models.DecimalField(default=0, verbose_name='٪ بیمه سهم سازمان', **RATE)
    life_insurance_employee = models.DecimalField(default=0, verbose_name='بیمه عمر سهم فرد', **MONEY)
    life_insurance_org = models.DecimalField(default=0, verbose_name='بیمه عمر سهم سازمان', **MONEY)
    housing_installment = models.DecimalField(default=0, verbose_name='قسط مسکن ماهانه', **MONEY)
    medical_main = models.DecimalField(default=0, verbose_name='بیمه درمانی اصلی', **MONEY)
    medical_dep1 = models.DecimalField(default=0, verbose_name='بیمه درمانی تبعی یک', **MONEY)
    medical_dep2 = models.DecimalField(default=0, verbose_name='بیمه درمانی تبعی دو', **MONEY)
    medical_dep3 = models.DecimalField(default=0, verbose_name='بیمه درمانی تبعی سه', **MONEY)
    supplementary_amount = models.DecimalField(default=0, verbose_name='بیمه تکمیلی ماهانه', **MONEY)
    tax_amount = models.DecimalField(default=0, verbose_name='مالیات متعلقه (از سامانه مالیاتی)', **MONEY)


class MonthlyAttendance(models.Model):
    """کارکرد: hours and days of one employee in one month, plus the bonus and welfare percentages."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    ot_normal = models.DecimalField(default=0, verbose_name='اضافه کار عادی (ساعت)', **RATE)
    ot_holiday = models.DecimalField(default=0, verbose_name='اضافه کار تعطیل (ساعت)', **RATE)
    ot_incentive = models.DecimalField(default=0, verbose_name='اضافه کار تشویقی (ساعت)', **RATE)
    holiday_work_days = models.DecimalField(default=0, verbose_name='جمع کاری (روز)', **RATE)
    night_hours = models.DecimalField(default=0, verbose_name='شب کاری (ساعت)', **RATE)
    absent_days = models.DecimalField(default=0, verbose_name='غیبت (روز)', **RATE)
    sick_days = models.DecimalField(default=0, verbose_name='مرخصی استعلاجی (روز)', **RATE)
    worked_days = models.DecimalField(default=0, verbose_name='کارکرد (روز)', **RATE)   # 0 = full month
    bonus_pct = models.DecimalField(default=0, verbose_name='کارانه (٪)', **RATE)
    welfare_pct = models.DecimalField(default=0, verbose_name='رفاهیات (٪)', **RATE)

    class Meta:
        ordering = ['year', 'month', 'employee']
        constraints = [models.UniqueConstraint(fields=['employee', 'year', 'month'], name='uniq_attendance_month'),
                       models.CheckConstraint(condition=Q(month__gte=1, month__lte=12), name='attendance_month_range')]


class Mission(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='missions')
    order_no = models.CharField(max_length=40, verbose_name='شماره حکم')
    order_date = models.DateField(verbose_name='تاریخ حکم')
    start_date = models.DateField(verbose_name='تاریخ شروع')
    end_date = models.DateField(verbose_name='تاریخ خاتمه')
    origin = models.CharField(max_length=80, verbose_name='شهر مبدا')
    destination = models.CharField(max_length=80, verbose_name='شهر مقصد')
    distance_km = models.PositiveIntegerField(default=0, verbose_name='فاصله بین دو شهر (کیلومتر)')
    driving_right = models.BooleanField(default=False, verbose_name='مسئول حق رانندگی')
    bad_weather = models.DecimalField(default=0, verbose_name='بدی آب و هوا', **MONEY)
    misc_cost = models.DecimalField(default=0, verbose_name='هزینه متفرقه', **MONEY)

    class Meta:
        ordering = ['-start_date', 'id']
        constraints = [models.CheckConstraint(condition=Q(end_date__gte=models.F('start_date')), name='mission_dates_ordered')]

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1


class SpecialAllowance(models.Model):
    """مزایای مخصوص: an allowance added to every active employee of a calculation group."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='special_allowances')
    calc_group = models.CharField(max_length=20, choices=CALC_GROUPS, verbose_name='گروه محاسباتی')
    title = models.CharField(max_length=100, verbose_name='عنوان مزایا')
    amount = models.DecimalField(verbose_name='مبلغ', **MONEY)

    class Meta:
        ordering = ['calc_group', 'id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='special_allowance_positive')]


class SpecialDebt(models.Model):
    """بدهی مخصوص: a monthly deduction applied to every active employee of a group from its start month."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='special_debts')
    calc_group = models.CharField(max_length=20, choices=CALC_GROUPS, verbose_name='گروه محاسباتی')
    title = models.CharField(max_length=100, verbose_name='عنوان بدهی')
    installment = models.DecimalField(verbose_name='مبلغ قسط', **MONEY)
    org_share = models.DecimalField(default=0, verbose_name='سهم سازمان', **MONEY)
    start_year = models.PositiveSmallIntegerField(verbose_name='سال')
    start_month = models.PositiveSmallIntegerField(verbose_name='ماه')
    months = models.PositiveSmallIntegerField(default=12, verbose_name='تعداد ماه')
    note = models.CharField(max_length=300, blank=True, verbose_name='توضیحات')

    class Meta:
        ordering = ['calc_group', 'id']
        constraints = [models.CheckConstraint(condition=Q(installment__gt=0), name='special_debt_positive'),
                       models.CheckConstraint(condition=Q(months__gte=1), name='special_debt_months')]


class MiscPayment(models.Model):
    """پرداخت متفرقه: an extra transfer to the employee (not insurable) and an advance deducted in the same month."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='misc_payments')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    transfer_amount = models.DecimalField(default=0, verbose_name='مبلغ واریزی', **MONEY)
    advance = models.DecimalField(default=0, verbose_name='علی‌الحساب', **MONEY)

    class Meta:
        ordering = ['year', 'month', 'employee']
        constraints = [models.UniqueConstraint(fields=['employee', 'year', 'month'], name='uniq_misc_payment_month')]


class DailyWorker(models.Model):
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='daily_workers')
    row = models.PositiveIntegerField(verbose_name='ردیف')
    first_name = models.CharField(max_length=100, verbose_name='نام')
    last_name = models.CharField(max_length=100, verbose_name='نام خانوادگی')
    father_name = models.CharField(max_length=100, blank=True, verbose_name='نام پدر')
    id_card_no = models.CharField(max_length=20, blank=True, verbose_name='شماره شناسنامه')
    national_id = models.CharField(max_length=10, verbose_name='شماره ملی')
    gender = models.CharField(max_length=1, choices=Employee.GENDERS, default='m', verbose_name='جنسیت')
    insurance_no = models.CharField(max_length=20, blank=True, verbose_name='شماره بیمه‌گری')
    job_title = models.CharField(max_length=100, blank=True, verbose_name='عنوان شغل')
    account_no = models.CharField(max_length=40, blank=True, verbose_name='شماره حساب')
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['row']
        constraints = [models.UniqueConstraint(fields=['municipality', 'row'], name='uniq_daily_worker_row'),
                       models.UniqueConstraint(fields=['municipality', 'national_id'], name='uniq_daily_worker_nid')]

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()


class DailyWorkerMonth(models.Model):
    """One month of a daily worker: pay = wage x days + overtime + housing + grocery; deductions are entered figures."""
    worker = models.ForeignKey(DailyWorker, on_delete=models.CASCADE, related_name='months')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    daily_wage = models.DecimalField(verbose_name='دستمزد روزانه', **MONEY)
    days = models.DecimalField(verbose_name='تعداد روز کارکرد', **RATE)
    overtime_hours = models.DecimalField(default=0, verbose_name='ساعت اضافه کار', **RATE)
    housing = models.DecimalField(default=0, verbose_name='حق مسکن', **MONEY)
    grocery = models.DecimalField(default=0, verbose_name='حق خواربار', **MONEY)
    advance = models.DecimalField(default=0, verbose_name='علی‌الحساب', **MONEY)
    insurance_employee = models.DecimalField(default=0, verbose_name='بیمه سهم فرد', **MONEY)
    insurance_org = models.DecimalField(default=0, verbose_name='بیمه سهم سازمان', **MONEY)
    tax_pct = models.DecimalField(default=0, verbose_name='درصد مالیات', **RATE)
    pay_date = models.DateField(null=True, blank=True, verbose_name='تاریخ پرداخت')
    gross = models.DecimalField(default=0, **MONEY)
    tax = models.DecimalField(default=0, **MONEY)
    net = models.DecimalField(default=0, **MONEY)

    class Meta:
        ordering = ['year', 'month', 'worker']
        constraints = [models.UniqueConstraint(fields=['worker', 'year', 'month'], name='uniq_daily_worker_month')]


class EidiSetting(models.Model):
    """Inputs of the Eidi bonus for one calculation group and year."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='eidi_settings')
    year = models.PositiveSmallIntegerField()
    calc_group = models.CharField(max_length=20, choices=CALC_GROUPS, verbose_name='گروه محاسباتی')
    fixed_amount = models.DecimalField(verbose_name='مقدار ثابت (عیدی یک سال کامل)', **MONEY)
    cap = models.DecimalField(default=0, verbose_name='سقف عیدی (۰ = بدون سقف)', **MONEY)
    annual_days = models.PositiveSmallIntegerField(default=360, verbose_name='کارکرد سالانه (روز)')
    advance = models.DecimalField(default=0, verbose_name='علی‌الحساب عیدی', **MONEY)

    class Meta:
        ordering = ['year', 'calc_group']
        constraints = [models.UniqueConstraint(fields=['municipality', 'year', 'calc_group'], name='uniq_eidi_group_year'),
                       models.CheckConstraint(condition=Q(annual_days__gte=1), name='eidi_annual_days')]


class EidiRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='eidi')
    year = models.PositiveSmallIntegerField()
    worked_days = models.DecimalField(default=0, verbose_name='کارکرد', **RATE)
    absent_days = models.DecimalField(default=0, verbose_name='غیبت', **RATE)
    sick_days = models.DecimalField(default=0, verbose_name='استعلاجی', **RATE)
    amount = models.DecimalField(default=0, **MONEY)

    class Meta:
        ordering = ['year', 'employee']
        constraints = [models.UniqueConstraint(fields=['employee', 'year'], name='uniq_eidi_employee_year')]


class PayrollRun(models.Model):
    """The computed payroll of one month. Draft runs can be recomputed or deleted; a final run is the archive."""
    STATUSES = [('draft', 'محاسبه‌شده'), ('final', 'قطعی')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='payroll_runs')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=6, choices=STATUSES, default='draft')
    insurance_uploaded = models.BooleanField(default=False, verbose_name='لیست بیمه بارگذاری شد')
    tax_uploaded = models.BooleanField(default=False, verbose_name='لیست مالیات بارگذاری شد')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-year', '-month']
        constraints = [models.UniqueConstraint(fields=['municipality', 'year', 'month'], name='uniq_payroll_month'),
                       models.CheckConstraint(condition=Q(month__gte=1, month__lte=12), name='payroll_month_range')]


class PayrollSlip(models.Model):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='slips')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='slips')
    allowances = models.DecimalField(default=0, **MONEY)
    special_allowances = models.DecimalField(default=0, **MONEY)
    overtime = models.DecimalField(default=0, **MONEY)
    night_work = models.DecimalField(default=0, **MONEY)
    holiday_work = models.DecimalField(default=0, **MONEY)
    bonus = models.DecimalField(default=0, **MONEY)
    mission = models.DecimalField(default=0, **MONEY)
    misc_transfer = models.DecimalField(default=0, **MONEY)
    gross = models.DecimalField(default=0, **MONEY)
    insurable = models.DecimalField(default=0, **MONEY)
    insurance_employee = models.DecimalField(default=0, **MONEY)
    insurance_org = models.DecimalField(default=0, **MONEY)
    medical = models.DecimalField(default=0, **MONEY)
    supplementary = models.DecimalField(default=0, **MONEY)
    life_insurance = models.DecimalField(default=0, **MONEY)
    housing = models.DecimalField(default=0, **MONEY)
    debts = models.DecimalField(default=0, **MONEY)
    welfare = models.DecimalField(default=0, **MONEY)
    advance = models.DecimalField(default=0, **MONEY)
    tax = models.DecimalField(default=0, **MONEY)
    deductions = models.DecimalField(default=0, **MONEY)
    net = models.DecimalField(default=0, **MONEY)

    class Meta:
        ordering = ['employee__code']
        constraints = [models.UniqueConstraint(fields=['run', 'employee'], name='uniq_slip_employee'),
                       models.CheckConstraint(condition=Q(net__gte=0), name='slip_net_not_negative')]
