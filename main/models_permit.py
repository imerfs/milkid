"""The building-permit file (پرونده‌ی پروانه ساختمان): the people, the ownership paper, the shamim file and the stage.

One ``PermitFile`` belongs to one ``ServiceRequest`` of type ``building_permit`` (the request keeps the status, the
workflow history and the notifications; the file keeps what the permit process itself needs). Identity papers are kept
in the private storage (never served by /media/) and are shown only to the owner and to the village's staff.
"""
from django.conf import settings
from django.db import models

from .storage import PrivateStorage

# The nine steps of the permit process (the pages in main/templates/main/services/building-permits/). Only step 1 is
# handled by the system so far; the others are listed so the file shows where it is going.
STAGES = [
    (1, 'افتتاح پرونده'),
    (2, 'تأیید مالکیت و مدارک مکان‌محور'),
    (3, 'استعلام بنیاد مسکن'),
    (4, 'نقشه‌ها و برآورد هزینه'),
    (5, 'پرداخت یکپارچه'),
    (6, 'بیمه تأمین اجتماعی'),
    (7, 'پروانه و نظارت بر ساخت'),
    (8, 'خدمات و اختتامیه'),
    (9, 'درخواست پایان کار'),
]

# Construction without a permit (ساخت‌وساز بدون پروانه) follows the Article 99 commission instead (the pages in
# main/templates/main/services/construction-without-permit/). Only step 1 is handled by the system so far.
UNLICENSED_STAGES = [
    (1, 'ایجاد پرونده اولیه'),
    (2, 'تأیید مالکیت و مدارک مکان‌محور'),
    (3, 'درخواست کمیسیون ماده ۹۹ و بازدید'),
    (4, 'تعهد، استحکام بنا، رأی و جریمه'),
    (5, 'خدمات و اختتامیه'),
    (6, 'درخواست پایان کار'),
]


class PermitFile(models.Model):
    TRACKS = [('permit', 'پروانه ساختمان'), ('unlicensed', 'ساخت‌وساز بدون پروانه')]
    OWNERSHIP = [
        ('deed', 'سند مالکیت'),
        ('agreement', 'قولنامه (بنگاهی / عادی)'),
        ('bonyad', 'قرارداد واگذاری بنیاد مسکن'),
    ]
    KINDS = [('construction', 'پروانه احداث بنا'), ('demolition', 'پروانه تخریب'), ('repair', 'پروانه تعمیر')]
    LAND_USES = [('residential', 'مسکونی'), ('administrative', 'اداری'), ('commercial', 'تجاری'), ('services', 'خدماتی')]
    # state of the current step: waiting for the staff, sent back for missing papers, done (the file moves on), refused
    STATES = [('submitted', 'در انتظار بررسی'), ('needs_docs', 'نیاز به رفع نقص'), ('done', 'مرحله انجام شد'),
              ('rejected', 'رد شده')]

    request = models.OneToOneField('main.ServiceRequest', on_delete=models.CASCADE, related_name='permit_file')
    stage_no = models.PositiveSmallIntegerField(default=1, verbose_name='مرحله فعلی')
    state = models.CharField(max_length=12, choices=STATES, default='submitted', verbose_name='وضعیت مرحله')
    permit_kind = models.CharField(max_length=14, choices=KINDS, default='construction', verbose_name='نوع پروانه')
    track = models.CharField(max_length=10, choices=TRACKS, default='permit', db_index=True, verbose_name='مسیر پرونده')

    ownership_type = models.CharField(max_length=10, choices=OWNERSHIP, verbose_name='مدرک مالکیت')
    doc_number = models.CharField(max_length=60, blank=True, verbose_name='شماره سند / قرارداد')
    doc_date = models.CharField(max_length=10, blank=True, verbose_name='تاریخ سند / قرارداد')
    doc_issuer = models.CharField(max_length=150, blank=True, verbose_name='مرجع صدور')
    project_code = models.CharField(max_length=40, blank=True, verbose_name='کد پروژه (بنیاد مسکن)')
    registry_plot = models.CharField(max_length=60, blank=True, verbose_name='پلاک ثبتی (فرعی از اصلی)')
    lot_number = models.CharField(max_length=10, blank=True, verbose_name='شماره قطعه‌ی تفکیکی')
    share_dang = models.CharField(max_length=10, blank=True, verbose_name='سهم (دانگ)')
    area_m2 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='مساحت (مترمربع)')
    land_use = models.CharField(max_length=14, choices=LAND_USES, blank=True, verbose_name='کاربری')
    address = models.TextField(blank=True, verbose_name='آدرس ملک')
    postal_code = models.CharField(max_length=10, blank=True, verbose_name='کد پستی')
    # the four limits (حدود اربعه) and anything else the paper says (lease years, unit count ...)
    details = models.JSONField(default=dict, blank=True)

    # given by the clerk from the shamim file; ``parcel`` is the plot of the village map it belongs to (if it is drawn)
    renewal_code = models.CharField(max_length=40, blank=True, db_index=True, verbose_name='کد نوسازی')
    parcel = models.ForeignKey('main.MapParcel', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='permit_files', verbose_name='قطعه در نقشه')
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    opened_at = models.DateTimeField(null=True, blank=True)
    staff_notes = models.TextField(blank=True, verbose_name='یادداشت کارشناس')
    # what reading the shamim file found (area, outline, plots of the map it lies on), see main/office/shamim.py
    shamim_info = models.JSONField(default=dict, blank=True)
    # step 2: form 1 (the dehyari's enquiry to Bonyad-e Maskan) and form 2 (the owner's request), as filled in
    step2 = models.JSONField(default=dict, blank=True)
    form1_at = models.DateTimeField(null=True, blank=True)
    form2_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='تحویل فرم‌های امضاشده')
    # step 3: the Bonyad-e Maskan's answer (form الف۲-۱) as the owner typed it from the letter, and where it stands
    BONYAD_STATES = [('', 'منتظر پاسخ بنیاد'), ('uploaded', 'منتظر تایید صحت'), ('rejected', 'برگشت‌خورده'), ('verified', 'تایید شد')]
    bonyad = models.JSONField(default=dict, blank=True)
    bonyad_state = models.CharField(max_length=10, choices=BONYAD_STATES, blank=True, default='')
    bonyad_at = models.DateTimeField(null=True, blank=True, verbose_name='ارسال پاسخ بنیاد')
    bonyad_checked_at = models.DateTimeField(null=True, blank=True)
    bonyad_checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # step 4: the plans, the engineers, forms 04-07 and the dehyari's signature (main/office/permit_step4.py)
    DESIGN_STATES = [('', 'در حال تهیه‌ی نقشه'), ('submitted', 'منتظر بررسی نقشه‌ها'), ('returned', 'برگشت‌خورده'),
                     ('reviewed', 'منتظر امضای دهیار'), ('signed', 'امضا شد')]
    design = models.JSONField(default=dict, blank=True)
    design_state = models.CharField(max_length=10, choices=DESIGN_STATES, blank=True, default='')
    design_at = models.DateTimeField(null=True, blank=True)
    design_reviewed_at = models.DateTimeField(null=True, blank=True)
    design_reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    design_signed_at = models.DateTimeField(null=True, blank=True)
    design_signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # step 5: the fee rows the financial officer defines for the owner, and the owner's answer (main/office/permit_step5.py)
    FEES_STATES = [('', 'منتظر تعیین عوارض'), ('offered', 'منتظر تایید متقاضی'), ('objected', 'اعتراض متقاضی'), ('approved', 'تایید شد')]
    fees = models.JSONField(default=dict, blank=True)
    fees_state = models.CharField(max_length=10, choices=FEES_STATES, blank=True, default='')
    fees_at = models.DateTimeField(null=True, blank=True, verbose_name='ارسال عوارض به متقاضی')
    fees_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    fees_approved_at = models.DateTimeField(null=True, blank=True)
    # step 6: the fee payments received and the introduction letter to the Social Security Organisation
    insurance = models.JSONField(default=dict, blank=True)
    # '' (paying) -> 'introduced' (letter issued) -> 'uploaded' (the owner's insurance certificate) -> 'verified' (step 7) / 'returned'
    INSURANCE_STATES = [('', 'پرداخت عوارض'), ('introduced', 'معرفی‌نامه صادر شد'), ('uploaded', 'گواهی منتظر تایید'), ('returned', 'گواهی برگشت‌خورده'), ('verified', 'گواهی تایید شد')]
    insurance_state = models.CharField(max_length=10, choices=INSURANCE_STATES, blank=True, default='')
    insurance_at = models.DateTimeField(null=True, blank=True)
    # step 7: the building permit form the dehyari prints (main/office/permit_step7.py)
    licence = models.JSONField(default=dict, blank=True)
    licence_state = models.CharField(max_length=8, blank=True, default='')           # '' or 'issued'
    licence_at = models.DateTimeField(null=True, blank=True)
    licence_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # the permit lasts one year; each renewal (at most two) is a request + a renewal form (main/office/permit_extension.py)
    extensions = models.JSONField(default=list, blank=True)
    # the supervision: the technical supervisor (inspector) following the work and forms 8-13 (main/office/permit_supervision.py)
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='supervised_permits')
    # the owner's requests for utility letters (electricity, gas, water) the dehyari signs (main/office/permit_services.py)
    services = models.JSONField(default=list, blank=True)
    # the end-of-work request and certificate (main/office/permit_endwork.py): '' / requested / approved / issued / rejected
    endwork = models.JSONField(default=dict, blank=True)
    endwork_state = models.CharField(max_length=10, blank=True, default='')
    supervision = models.JSONField(default=dict, blank=True)
    # construction without a permit, step 2: the owner's request form and undertaking, signed on paper and uploaded
    # (main/office/permit_commission.py): '' (the owner fills, prints, signs) / uploaded / returned / verified
    COMMISSION_STATES = [('', 'در حال تهیه‌ی فرم‌ها'), ('uploaded', 'منتظر تایید فرم‌ها'), ('returned', 'برگشت‌خورده'), ('verified', 'تایید شد')]
    commission = models.JSONField(default=dict, blank=True)
    commission_state = models.CharField(max_length=10, choices=COMMISSION_STATES, blank=True, default='')
    commission_at = models.DateTimeField(null=True, blank=True)
    # construction without a permit, step 3: the warning notice (اخطاریه به مالک) the owner already received, uploaded
    # (main/office/permit_notice.py): '' (waiting for the owner) / uploaded / returned / verified
    notice = models.JSONField(default=dict, blank=True)
    notice_state = models.CharField(max_length=10, choices=COMMISSION_STATES, blank=True, default='')
    notice_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'پرونده‌ی پروانه ساختمان'
        verbose_name_plural = 'پرونده‌های پروانه ساختمان'
        ordering = ['-created_at']

    def __str__(self):
        return f'پرونده {self.pk} - {self.request.user.get_full_name() or self.request.user.username}'

    @property
    def paid_up(self):
        """True when the confirmed payments cover the fees the owner approved."""
        pay = (self.insurance or {}).get('payments') or []
        total = (self.fees or {}).get('total') or 0
        return bool(total) and sum(p.get('amount', 0) for p in pay if p.get('ok')) >= total

    @property
    def unlicensed(self):
        return self.track == 'unlicensed'

    @property
    def stages(self):
        return UNLICENSED_STAGES if self.unlicensed else STAGES

    @property
    def status_text(self):
        """One line for the lists: where the file stands now."""
        if self.state != 'done':
            return self.get_state_display()
        if self.unlicensed:
            if self.stage_no == 2:
                return {'': 'منتظر فرم درخواست و تعهدنامه‌ی امضاشده (از متقاضی)', 'uploaded': 'فرم درخواست و تعهدنامه منتظر تایید',
                        'returned': 'فرم‌های امضاشده برگشت خورد'}.get(self.commission_state, '')
            if self.stage_no == 3:
                return {'': 'منتظر تصویر اخطاریه‌ی دریافتی (از متقاضی)', 'uploaded': 'اخطاریه منتظر تایید',
                        'returned': 'اخطاریه برگشت خورد'}.get(self.notice_state, '')
            return 'مرحله‌ی ۳ تایید شد؛ مرحله‌های بعدی در دست راه‌اندازی است'
        if self.stage_no >= 9:
            return {'': 'نظارت کامل شد؛ درخواست گواهی پایان کار از متقاضی', 'requested': 'درخواست پایان کار منتظر دهیاری', 'approved': 'گواهی پایان کار تایید شد؛ منتظر مهر و امضا',
                    'issued': 'گواهی پایان کار صادر شد', 'rejected': 'درخواست پایان کار رد شد'}.get(self.endwork_state, '')
        if self.stage_no >= 7:
            if self.licence_state != 'issued':
                return 'پروانه در حال تهیه (دهیاری)'
            from main.office import permit_extension       # pylint: disable=import-outside-toplevel
            return permit_extension.status_line(self)
        if self.stage_no == 6:
            if self.insurance_state:
                return {'introduced': 'منتظر گواهی تامین اجتماعی (از متقاضی)', 'uploaded': 'گواهی تامین اجتماعی منتظر تایید',
                        'returned': 'گواهی تامین اجتماعی برگشت خورد'}.get(self.insurance_state, '')
            return 'منتظر صدور معرفی‌نامه‌ی تامین اجتماعی' if self.paid_up else 'منتظر پرداخت عوارض'
        if self.stage_no == 5:
            return {'': 'منتظر تعیین عوارض (مسئول مالی)', 'offered': 'عوارض منتظر تایید متقاضی',
                    'objected': 'متقاضی به عوارض اعتراض کرد'}.get(self.fees_state, '')
        if self.stage_no == 4:
            return {'': 'نقشه‌ها در حال تهیه (متقاضی)', 'submitted': 'نقشه‌ها منتظر بررسی', 'returned': 'نقشه‌ها برگشت خورد',
                    'reviewed': 'منتظر امضای دهیار'}.get(self.design_state, '')
        if self.stage_no == 3:
            return {'': 'منتظر پاسخ بنیاد (از متقاضی)', 'uploaded': 'پاسخ بنیاد منتظر تایید صحت', 'rejected': 'پاسخ بنیاد برگشت خورد'}.get(self.bonyad_state, '')
        if self.delivered_at:
            return 'فرم‌ها تحویل شد'
        if self.stage_no == 2:
            if self.form1_at and self.form2_at:
                return 'فرم‌ها آماده‌ی امضا'
            return 'فرم ۱ ' + ('آماده' if self.form1_at else 'منتظر دهیاری') + ' · فرم ۲ ' + ('پر شد' if self.form2_at else 'منتظر متقاضی')
        return self.get_state_display()

    @property
    def needs_staff(self):
        """True while the village staff (clerk / expert / dehyari) have something to decide on this file."""
        if self.unlicensed:
            return (self.state == 'submitted' or (self.stage_no == 2 and self.commission_state == 'uploaded')
                    or (self.stage_no == 3 and self.notice_state == 'uploaded'))
        return (self.state == 'submitted' or (self.stage_no == 3 and self.bonyad_state == 'uploaded')
                or (self.stage_no == 4 and self.design_state in ('submitted', 'reviewed'))
                or (self.stage_no == 6 and self.insurance_state == 'uploaded')
                or (self.stage_no >= 7 and self.licence_state != 'issued')
                or (self.stage_no >= 7 and any(e.get('state') == 'requested' for e in self.extensions or []))
                or (self.stage_no >= 7 and any(s.get('state') == 'requested' for s in self.services or []))
                or (self.stage_no >= 9 and self.endwork_state in ('requested', 'approved'))
                or (self.stage_no == 7 and any(f.get('state') in ('uploaded', 'violation') for f in (self.supervision or {}).get('forms', {}).values()))
                or (self.stage_no == 6 and not self.insurance_state
                    and (self.paid_up or any(not p.get('ok') for p in (self.insurance or {}).get('payments') or []))))

    @property
    def needs_accountant(self):
        return not self.unlicensed and self.stage_no == 5 and self.fees_state in ('', 'objected')

    @property
    def stage_title(self):
        return dict(self.stages).get(self.stage_no, '')


class PermitPerson(models.Model):
    """A person named in the file: the applicant first, then the other owners."""
    ROLES = [('applicant', 'متقاضی'), ('co_owner', 'مالک دیگر / شریک'), ('spouse', 'همسر'),
             ('representative', 'وکیل / نماینده')]

    file = models.ForeignKey(PermitFile, on_delete=models.CASCADE, related_name='people')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    role = models.CharField(max_length=14, choices=ROLES, default='applicant')
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=80)
    father_name = models.CharField(max_length=60, blank=True)
    national_id = models.CharField(max_length=10)
    id_number = models.CharField(max_length=15, blank=True, verbose_name='شماره شناسنامه')
    birth_date = models.CharField(max_length=10, blank=True)
    birth_place = models.CharField(max_length=80, blank=True, verbose_name='محل صدور شناسنامه')
    phone = models.CharField(max_length=11, blank=True)
    email = models.EmailField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'شخص پرونده'
        verbose_name_plural = 'اشخاص پرونده'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()


def permit_upload_path(instance, filename):
    import uuid
    from pathlib import Path
    return f'permit_files/{instance.file_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


class PermitDocument(models.Model):
    KINDS = [
        ('national_card', 'کارت ملی'), ('birth_cert', 'شناسنامه'), ('deed', 'سند مالکیت'), ('agreement', 'قولنامه'),
        ('bonyad_contract', 'قرارداد بنیاد مسکن'), ('shamim', 'فایل شمیم'), ('bonyad_answer', 'پاسخ بنیاد مسکن'),
        ('warning_notice', 'اخطاریه به مالک'), ('comm_request', 'فرم درخواست امضاشده'), ('comm_undertake', 'تعهدنامه امضاشده'),
        ('plan_arch', 'نقشه‌ی معماری'), ('plan_struct', 'نقشه‌ی سازه'), ('plan_other', 'نقشه‌ی دیگر'), ('fee_receipt', 'فیش پرداخت عوارض'), ('insurance_cert', 'گواهی تامین اجتماعی'), ('supervision_form', 'فرم نظارت امضاشده'),
        ('other', 'سایر'),
    ]

    file = models.ForeignKey(PermitFile, on_delete=models.CASCADE, related_name='documents')
    person = models.ForeignKey(PermitPerson, null=True, blank=True, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=16, choices=KINDS)
    document = models.FileField(upload_to=permit_upload_path, storage=PrivateStorage())
    original_name = models.CharField(max_length=200)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['kind', 'id']
        verbose_name = 'مدرک پرونده'
        verbose_name_plural = 'مدارک پرونده'
