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
    (7, 'پروانه، نظارت و خدمات'),
    (8, 'خدمات و اختتامیه'),
    (9, 'درخواست پایان کار'),
]


class PermitFile(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'پرونده‌ی پروانه ساختمان'
        verbose_name_plural = 'پرونده‌های پروانه ساختمان'
        ordering = ['-created_at']

    def __str__(self):
        return f'پرونده {self.pk} - {self.request.user.get_full_name() or self.request.user.username}'

    @property
    def stage_title(self):
        return dict(STAGES).get(self.stage_no, '')


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
        ('bonyad_contract', 'قرارداد بنیاد مسکن'), ('shamim', 'فایل شمیم'), ('other', 'سایر'),
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
