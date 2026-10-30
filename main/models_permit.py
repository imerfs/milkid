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
    (2, 'فرم درخواست و تعهدنامه'),
    (3, 'اخطاریه و درخواست بازدید'),
    (4, 'گزارش بازدید، پیش‌آمدگی و مصالح'),
    (5, 'معرفی به کارشناس دادگستری و تعهدات'),
    (6, 'پاسخ کارشناس دادگستری و استحکام بنا'),
    (7, 'پرداخت عوارض و بهای خدمات'),
    (8, 'لیست بازدید بنیاد و نامه‌ی بنیاد'),
    (9, 'رأی کمیسیون، جریمه و پایان کار'),
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
    # construction without a permit, step 1: the owner's defence form (فرم دفاعیه) as filled in (main/office/permit_defence.py), and
    # the shamim sketch (کروکی شمیم) the owner asks the technical expert for when he has no shamim file (main/office/permit_sketch.py):
    # '' / requested / priced (the fee is set) / paid (the slip is recorded) / delivered
    SKETCH_STATES = [('', 'بدون درخواست کروکی'), ('requested', 'منتظر تعیین هزینه'), ('priced', 'منتظر پرداخت متقاضی'),
                     ('paid', 'منتظر تایید پرداخت و تحویل کروکی'), ('delivered', 'کروکی تحویل شد')]
    defence = models.JSONField(default=dict, blank=True)
    sketch = models.JSONField(default=dict, blank=True)
    sketch_state = models.CharField(max_length=10, choices=SKETCH_STATES, blank=True, default='')
    sketch_at = models.DateTimeField(null=True, blank=True)
    # construction without a permit, step 2: the owner's request form and undertaking, signed on paper and uploaded
    # (main/office/permit_commission.py): '' (the owner fills, prints, signs) / uploaded / returned / verified
    COMMISSION_STATES = [('', 'در حال تهیه‌ی فرم‌ها'), ('uploaded', 'منتظر تایید فرم‌ها'), ('returned', 'برگشت‌خورده'), ('verified', 'تایید شد')]
    commission = models.JSONField(default=dict, blank=True)
    commission_state = models.CharField(max_length=10, choices=COMMISSION_STATES, blank=True, default='')
    commission_at = models.DateTimeField(null=True, blank=True)
    # construction without a permit, step 3: the warning notice (اخطاریه به مالک) the owner already received, uploaded
    # (main/office/permit_notice.py): '' (waiting for the owner) / uploaded / returned / verified
    # '' (the owner uploads the one he has, or asks for one) / requested (he asks the village to issue it) / issued (the staff filled and
    # printed it; the owner signs in person) / uploaded (the signed scan) / returned / verified; then the owner asks for the technical
    # expert's visit: visit_state '' / requested / scheduled / done (which moves the file to step 4)
    NOTICE_STATES = [('', 'منتظر اخطاریه'), ('requested', 'درخواست صدور اخطاریه'), ('issued', 'اخطاریه صادر شد'), ('uploaded', 'منتظر تایید اخطاریه'),
                     ('returned', 'برگشت‌خورده'), ('verified', 'تایید شد')]
    VISIT_STATES = [('', 'بدون درخواست بازدید'), ('requested', 'درخواست بازدید'), ('scheduled', 'بازدید زمان‌بندی شد'), ('done', 'بازدید انجام شد')]
    notice = models.JSONField(default=dict, blank=True)
    notice_state = models.CharField(max_length=10, choices=NOTICE_STATES, blank=True, default='')
    notice_at = models.DateTimeField(null=True, blank=True)
    visit = models.JSONField(default=dict, blank=True)
    visit_state = models.CharField(max_length=10, choices=VISIT_STATES, blank=True, default='')
    visit_at = models.DateTimeField(null=True, blank=True)
    # construction without a permit, step 4 (main/office/permit_report.py, permit_site.py): the technical expert's visit report put in the
    # owner's file ('' / filed); the electricity office's answer when the building has an overhang over the street; the materials the owner
    # must clear from the street (both: '' none needed / required / replied|uploaded / returned / verified)
    REPORT_STATES = [('', 'گزارش بازدید تهیه نشده'), ('filed', 'گزارش در پرونده است')]
    SITE_STATES = [('', 'لازم نیست'), ('required', 'لازم است'), ('replied', 'پاسخ منتظر تایید'), ('uploaded', 'عکس منتظر تایید'),
                   ('returned', 'برگشت‌خورده'), ('verified', 'تایید شد')]
    report = models.JSONField(default=dict, blank=True)
    report_state = models.CharField(max_length=8, choices=REPORT_STATES, blank=True, default='')
    report_at = models.DateTimeField(null=True, blank=True)
    overhang = models.JSONField(default=dict, blank=True)
    overhang_state = models.CharField(max_length=10, choices=SITE_STATES, blank=True, default='')
    materials = models.JSONField(default=dict, blank=True)
    materials_state = models.CharField(max_length=10, choices=SITE_STATES, blank=True, default='')
    # construction without a permit, step 5 (main/office/permit_commit.py): the owner is introduced to a judiciary expert from the
    # dehyari's list (expert_state '' / introduced), fills the neighbours' consent form and takes the notarial undertaking to the notary
    # (consent_state / deed_state '' / uploaded / returned / verified)
    EXPERT_STATES = [('', 'منتظر معرفی به کارشناس'), ('introduced', 'به کارشناس معرفی شد')]
    COMMIT_STATES = [('', 'منتظر متقاضی'), ('uploaded', 'منتظر تایید'), ('returned', 'برگشت‌خورده'), ('verified', 'تایید شد')]
    commit = models.JSONField(default=dict, blank=True)
    expert_state = models.CharField(max_length=10, choices=EXPERT_STATES, blank=True, default='')
    consent_state = models.CharField(max_length=10, choices=COMMIT_STATES, blank=True, default='')
    deed_state = models.CharField(max_length=10, choices=COMMIT_STATES, blank=True, default='')
    # step 6 (main/office/permit_reply.py): the expert's two replies (the covering letter and table 2), uploaded by the owner who has handed
    # the originals to the dehyari; the strength verdict and the letter's number and date are kept in ``commit['reply']``
    reply_state = models.CharField(max_length=10, choices=COMMIT_STATES, blank=True, default='')
    # step 7 (main/office/permit_dues.py): the fee sheet of the dehyari («فرم محاسبه عوارض و بهای خدمات»), the owner's payments, the instalment
    # plan and its cheques, all kept in ``dues``; dues_state '' (sheet not issued) / issued; plan_state follows the instalment request
    DUES_STATES = [('', 'منتظر محاسبه‌ی عوارض'), ('issued', 'عوارض اعلام شد')]
    PLAN_STATES = [('', 'بدون تقسیط'), ('requested', 'درخواست تقسیط'), ('approved', 'تقسیط تایید شد'), ('signed', 'تقسیط امضا شد'),
                   ('registered', 'چک‌ها ثبت شد'), ('confirmed', 'ثبت چک‌ها تایید شد'), ('returned', 'تقسیط برگشت خورد')]
    dues = models.JSONField(default=dict, blank=True)
    dues_state = models.CharField(max_length=10, choices=DUES_STATES, blank=True, default='')
    plan_state = models.CharField(max_length=10, choices=PLAN_STATES, blank=True, default='')
    # step 8 (main/office/permit_bonyad.py): the owner asks to be put on the Bonyad-e Maskan's visit list; once the visit is done the technical expert releases
    # the package (sketch, expert's reply, visit report, payments, the dehyari's letter) to the owner, who then uploads the Bonyad's letter
    BONYAD_STATES = [('', 'منتظر درخواست متقاضی'), ('requested', 'در لیست بازدید بنیاد'), ('released', 'مدارک به متقاضی نشان داده شد'),
                     ('uploaded', 'نامه‌ی بنیاد منتظر تایید'), ('returned', 'نامه‌ی بنیاد برگشت خورد'), ('verified', 'نامه‌ی بنیاد تایید شد')]
    bonyad_list = models.JSONField(default=dict, blank=True)
    bonyad_list_state = models.CharField(max_length=10, choices=BONYAD_STATES, blank=True, default='')
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
        if self.unlicensed and self.stage_no == 1:
            return self.step1_text()
        if self.state != 'done':
            return self.get_state_display()
        if self.unlicensed:
            if self.stage_no == 2:
                return {'': 'منتظر فرم درخواست و تعهدنامه‌ی امضاشده (از متقاضی)', 'uploaded': 'فرم درخواست و تعهدنامه منتظر تایید',
                        'returned': 'فرم‌های امضاشده برگشت خورد'}.get(self.commission_state, '')
            if self.stage_no == 3:
                if self.notice_state == 'verified':
                    return {'': 'منتظر درخواست بازدید (از متقاضی)', 'requested': 'درخواست بازدید منتظر کارشناس فنی',
                            'scheduled': 'بازدید زمان‌بندی شد'}.get(self.visit_state, '')
                return {'': 'منتظر اخطاریه‌ی قبلی یا درخواست صدور اخطاریه (از متقاضی)', 'requested': 'درخواست اخطاریه منتظر صدور (دهیاری)',
                        'issued': 'اخطاریه صادر شد؛ متقاضی حضوری امضا کند', 'uploaded': 'اخطاریه منتظر تایید',
                        'returned': 'اخطاریه برگشت خورد'}.get(self.notice_state, '')
            if self.stage_no == 4:
                return self.step4_text()
            if self.stage_no == 5:
                return self.step5_text()
            if self.stage_no == 8:
                return {'': 'منتظر درخواست قرار گرفتن در لیست بازدید بنیاد (از متقاضی)', 'requested': 'در لیست بازدید بنیاد؛ منتظر تایید انجام بازدید (کارشناس فنی)',
                        'released': 'مدارک به متقاضی نشان داده شد؛ منتظر نامه‌ی بنیاد (از متقاضی)', 'uploaded': 'نامه‌ی بنیاد منتظر تایید',
                        'returned': 'نامه‌ی بنیاد برگشت خورد', 'verified': 'نامه‌ی بنیاد تایید شد؛ منتظر تایید نهایی مرحله'}.get(self.bonyad_list_state, '')
            if self.stage_no == 7:
                return self.step7_text()
            if self.stage_no == 6:
                return {'': 'منتظر دو جوابیه‌ی کارشناس دادگستری (از متقاضی)', 'uploaded': 'جوابیه‌های کارشناس منتظر تایید', 'returned': 'جوابیه‌ها برگشت خورد',
                        'verified': 'جوابیه‌ها تایید شد؛ منتظر تایید نهایی مرحله'}.get(self.reply_state, '')
            return f'مرحله‌ی {"۰۱۲۳۴۵۶۷۸۹"[self.stage_no - 1]} تایید شد؛ مرحله‌های بعدی در دست راه‌اندازی است'
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
            return (self.state == 'submitted' or self.sketch_state in ('requested', 'paid') or (self.stage_no == 2 and self.commission_state == 'uploaded')
                    or (self.stage_no == 3 and (self.notice_state in ('requested', 'uploaded') or self.visit_state in ('requested', 'scheduled')))
                    or (self.stage_no == 4 and (self.report_state != 'filed' or self.overhang_state == 'replied' or self.materials_state == 'uploaded'
                                                or (self.overhang_state in ('', 'verified') and self.materials_state in ('', 'verified'))))
                    or (self.stage_no == 5 and (self.expert_state == '' or self.consent_state == 'uploaded' or self.deed_state == 'uploaded'
                                                or (self.consent_state == 'verified' and self.deed_state == 'verified')))
                    or (self.stage_no == 6 and self.reply_state in ('uploaded', 'verified'))
                    or (self.stage_no == 8 and self.bonyad_list_state in ('requested', 'uploaded', 'verified'))
                    or (self.stage_no == 7 and (self.plan_state == 'requested' or self.dues_settled
                                                or any(not p.get('ok') for p in (self.dues or {}).get('payments') or []))))
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

    def step1_text(self):
        """Where an unlicensed file stands in step 1: what the owner or the staff still have to do."""
        if self.state != 'submitted':
            return self.get_state_display()
        if self.sketch_state and self.sketch_state != 'delivered':
            return dict(self.SKETCH_STATES)[self.sketch_state]
        if not self.documents.filter(kind='defence_form').exists():
            return 'منتظر فرم دفاعیه‌ی امضاشده (از متقاضی)'
        return 'در انتظار بررسی'

    def step4_text(self):
        """Where an unlicensed file stands in step 4: the report, the electricity office's answer, the materials, the confirmation."""
        if self.report_state != 'filed':
            return 'منتظر گزارش بازدید (کارشناس فنی)'
        waiting = []
        if self.overhang_state in ('required', 'returned'):
            waiting.append('پاسخ اداره برق (از متقاضی)')
        if self.materials_state in ('required', 'returned'):
            waiting.append('عکس جمع‌آوری مصالح (از متقاضی)')
        if waiting:
            return 'منتظر ' + ' و '.join(waiting)
        if self.overhang_state == 'replied' or self.materials_state == 'uploaded':
            return 'مدارک متقاضی منتظر تایید'
        return 'گزارش در پرونده است؛ منتظر تایید نهایی مرحله'

    @property
    def dues_total(self):
        return int(((self.dues or {}).get('sheet') or {}).get('total') or 0)

    @property
    def dues_paid(self):
        return sum(p.get('amount', 0) for p in (self.dues or {}).get('payments') or [] if p.get('ok'))

    @property
    def dues_settled(self):
        """The fees are covered: paid in full, or the instalment plan's cheques are registered and confirmed."""
        return self.dues_state == 'issued' and (self.dues_paid >= self.dues_total or self.plan_state == 'confirmed')

    @property
    def needs_accountant_dues(self):
        """Step 7 of an unlicensed file, for the financial officer: the sheet to issue, the plan to sign, the cheques to confirm."""
        return self.unlicensed and self.stage_no == 7 and (self.dues_state == '' or self.plan_state in ('approved', 'registered')
                                                           or any(not p.get('ok') for p in (self.dues or {}).get('payments') or []))

    def step7_text(self):
        """Where an unlicensed file stands in step 7: the fees, the payments, the instalment plan."""
        if self.dues_state == '':
            return 'منتظر محاسبه‌ی عوارض و بهای خدمات (مسئول مالی)'
        if self.dues_settled:
            return 'عوارض تسویه شد؛ منتظر تایید نهایی مرحله'
        plan = {'requested': 'درخواست تقسیط منتظر تایید کارشناس اداری یا دهیار', 'approved': 'تقسیط منتظر امضای مسئول مالی',
                'signed': 'تقسیط تایید شد؛ منتظر ثبت چک‌ها (از متقاضی)', 'registered': 'چک‌ها منتظر تایید ثبت (مسئول مالی)',
                'returned': 'درخواست تقسیط برگشت خورد'}.get(self.plan_state)
        if plan:
            return plan
        if any(not p.get('ok') for p in (self.dues or {}).get('payments') or []):
            return 'فیش پرداخت منتظر تایید'
        return 'منتظر پرداخت عوارض (از متقاضی)'

    def step5_text(self):
        """Where an unlicensed file stands in step 5: the introduction, the neighbours' consent, the notarial undertaking."""
        waiting = []
        if self.expert_state != 'introduced':
            waiting.append('معرفی به کارشناس دادگستری (دهیاری)')
        if self.consent_state in ('', 'returned'):
            waiting.append('تعهدنامه‌ی رضایت همسایگان (از متقاضی)')
        if self.deed_state in ('', 'returned'):
            waiting.append('تعهد محضری (از متقاضی)')
        if waiting:
            return 'منتظر ' + ' و '.join(waiting)
        if self.consent_state == 'uploaded' or self.deed_state == 'uploaded':
            return 'مدارک متقاضی منتظر تایید'
        return 'همه‌ی مدارک این مرحله تایید شد؛ منتظر تایید نهایی مرحله'

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
        ('bonyad_letter', 'نامه‌ی بنیاد مسکن'), ('expert_letter', 'نامه‌ی کارشناس دادگستری'), ('expert_table', 'جدول شماره ۲ کارشناس'), ('consent_form', 'تعهدنامه‌ی رضایت همسایگان'), ('deed_scan', 'تعهد محضری'), ('power_reply', 'پاسخ اداره برق'), ('materials_photo', 'عکس جمع‌آوری مصالح'), ('defence_form', 'فرم دفاعیه امضاشده'), ('sketch_slip', 'فیش هزینه‌ی کروکی'), ('warning_notice', 'اخطاریه به مالک'), ('comm_request', 'فرم درخواست امضاشده'), ('comm_undertake', 'تعهدنامه امضاشده'),
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


class JudicialExpert(models.Model):
    """A judiciary expert (کارشناس رسمی دادگستری) the dehyari of a village introduces owners of unlicensed buildings to."""
    city_village = models.CharField(max_length=120, db_index=True, verbose_name='روستا')
    name = models.CharField(max_length=120, verbose_name='نام کارشناس')
    field = models.CharField(max_length=120, blank=True, verbose_name='رشته / تخصص')
    phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن')
    active = models.BooleanField(default=True, verbose_name='فعال')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'کارشناس دادگستری'
        verbose_name_plural = 'کارشناسان دادگستری'

    def __str__(self):
        return self.name

