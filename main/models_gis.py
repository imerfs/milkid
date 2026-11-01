"""Village web-GIS: one surveyed map per village, its blocks and plots, and an archive for every plot.

The geometry comes from the municipality's drawing (scripts/gis/build_village_map.py writes the GeoJSON that
main/gis/loader.py loads). Permit, owner and fee data are not in the drawing: they are entered later through the
map's side panel, so those tables start empty. Imported at the end of main/models.py.
"""
from django.conf import settings
from django.db import models

from main.models_accounting import MONEY


class VillageMap(models.Model):
    """A village that has a surveyed map. Only staff of that village (and admins) may open it."""
    slug = models.SlugField(unique=True, verbose_name='شناسه')
    name = models.CharField(max_length=100, verbose_name='نام روستا')
    county_name = models.CharField(max_length=100, blank=True, verbose_name='شهرستان',
                                   help_text='برای تشخیص روستاهای هم‌نام در شهرستان‌های دیگر')
    city_village = models.ForeignKey('main.CityVillage', null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+', verbose_name='روستا در فهرست تقسیمات')
    centre_lat = models.FloatField(default=0)
    centre_lng = models.FloatField(default=0)
    source_note = models.CharField(max_length=300, blank=True, verbose_name='منبع نقشه')
    loaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'نقشه‌ی روستا'
        verbose_name_plural = 'نقشه‌های روستاها'

    def __str__(self):
        return self.name


class MapBlock(models.Model):
    village_map = models.ForeignKey(VillageMap, on_delete=models.CASCADE, related_name='blocks')
    number = models.CharField(max_length=10, verbose_name='شماره بلوک')
    zone = models.CharField(max_length=3, blank=True, verbose_name='محله',
                            help_text='بلوک‌های محله‌ی ۶ از ۱ شماره‌گذاری می‌شوند و با بلوک‌های دیگر یکی نیستند')
    parcel_count = models.PositiveIntegerField(default=0)
    area_m2 = models.FloatField(default=0)
    geometry = models.JSONField(verbose_name='هندسه (GeoJSON)')

    class Meta:
        verbose_name = 'بلوک'
        verbose_name_plural = 'بلوک‌ها'
        constraints = [models.UniqueConstraint(fields=['village_map', 'zone', 'number'], name='map_block_zone_unique')]

    def __str__(self):
        return f'بلوک {self.number}'


class LandUseClass(models.Model):
    """A land-use (کاربری) class of the drawing: its fill colour and, once known, what the colour means."""
    village_map = models.ForeignKey(VillageMap, on_delete=models.CASCADE, related_name='land_uses')
    key = models.CharField(max_length=6, verbose_name='رنگ (hex)')
    name = models.CharField(max_length=80, blank=True, verbose_name='نوع کاربری')
    plot_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'نوع کاربری'
        verbose_name_plural = 'انواع کاربری'
        constraints = [models.UniqueConstraint(fields=['village_map', 'key'], name='land_use_unique')]
        ordering = ['-plot_count']

    @property
    def color(self):
        return f'#{self.key}'

    def __str__(self):
        return self.name or f'کاربری با رنگ {self.color}'


class MapZone(models.Model):
    """A neighbourhood (محله) of the village; the drawing's zoning (حوزه‌بندی) is the same thing."""
    village_map = models.ForeignKey(VillageMap, on_delete=models.CASCADE, related_name='zones')
    number = models.CharField(max_length=3, verbose_name='شماره محله')
    name = models.CharField(max_length=80, blank=True, verbose_name='نام محله')
    block_count = models.PositiveIntegerField(default=0)
    parcel_count = models.PositiveIntegerField(default=0)
    geometry = models.JSONField(verbose_name='هندسه (GeoJSON)')

    class Meta:
        verbose_name = 'محله'
        verbose_name_plural = 'محله‌ها'
        constraints = [models.UniqueConstraint(fields=['village_map', 'number'], name='map_zone_unique')]

    def __str__(self):
        return self.name or f'محله {self.number}'


class MapEasement(models.Model):
    """A restricted strip or area (حریم) drawn in the detail drawing."""
    KINDS = [
        ('general', 'حریم'), ('quality', 'حریم کیفی'), ('qanat', 'حریم قنات'), ('qanat_quality', 'حریم کیفی قنات'),
        ('defense1', 'حریم پدافند غیرعامل (۱)'), ('defense2', 'حریم پدافند غیرعامل (۲)'),
    ]
    village_map = models.ForeignKey(VillageMap, on_delete=models.CASCADE, related_name='easements')
    kind = models.CharField(max_length=20, choices=KINDS)
    label = models.CharField(max_length=60)
    geometry = models.JSONField(verbose_name='هندسه (GeoJSON)')

    class Meta:
        verbose_name = 'حریم'
        verbose_name_plural = 'حریم‌ها'

    def __str__(self):
        return self.label


class MapParcel(models.Model):
    """One plot. ``uid`` is stable across reloads of the drawing so the archive stays attached to the plot."""
    KIND = [('drawn', 'ترسیم‌شده در نقشه'), ('estimated', 'تقریبی (مرز ترسیم نشده)')]

    village_map = models.ForeignKey(VillageMap, on_delete=models.CASCADE, related_name='parcels')
    uid = models.CharField(max_length=40)
    block_no = models.CharField(max_length=10, blank=True, db_index=True, verbose_name='بلوک')
    number = models.CharField(max_length=10, blank=True, verbose_name='شماره قطعه')
    renewal_code = models.CharField(max_length=40, blank=True, db_index=True, verbose_name='کد نوسازی')
    kind = models.CharField(max_length=10, choices=KIND, default='drawn')
    area_m2 = models.FloatField(default=0, verbose_name='مساحت (مترمربع)')
    other_numbers = models.JSONField(default=list, blank=True)
    duplicate_code = models.BooleanField(default=False)
    lot_no = models.CharField(max_length=10, blank=True, verbose_name='شماره قطعه‌ی تفکیکی')
    # '' = the village's own block-and-plot numbering; otherwise the key of a plot-number series (main/gis/series.py) whose plots are numbered 1, 2, 3 ... alone
    series = models.CharField(max_length=20, blank=True, default='', db_index=True, verbose_name='دسته‌ی شماره‌ی قطعه')
    permit_in_drawing = models.BooleanField(default=False, verbose_name='طبق نقشه پروانه صادر شده')
    # what a buyer is told (main/gis/inquiry.py): from the plan drawing by ``main.gis.plan_flags`` ("in the plan" = inside the plan's reserved areas, "exempt" =
    # the green-framed «مستثنیات» of the technical unit's drawing), never typed by citizens
    in_plan = models.BooleanField(default=False, db_index=True, verbose_name='داخل طرح')
    exempt = models.BooleanField(default=False, db_index=True, verbose_name='مستثنیات')
    # the renewal code is guild - apartment - plot - block - neighbourhood (صنف - آپارتمان - ملک - بلوک - محله)
    zone = models.CharField(max_length=3, blank=True, db_index=True, verbose_name='محله')
    guild_no = models.PositiveSmallIntegerField(default=0, verbose_name='صنف')
    apartment_no = models.PositiveSmallIntegerField(default=0, verbose_name='آپارتمان')
    land_use = models.ForeignKey(LandUseClass, null=True, blank=True, on_delete=models.SET_NULL, related_name='parcels',
                                 verbose_name='نوع کاربری')
    building_area_m2 = models.FloatField(default=0, verbose_name='مساحت اعیان (سطح اشغال)')
    building_count = models.PositiveSmallIntegerField(default=0)
    easement_hits = models.JSONField(default=list, blank=True, verbose_name='تداخل با حریم')
    first_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='سال شروع')
    last_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='آخرین سال')
    geometry = models.JSONField(verbose_name='هندسه (GeoJSON)')

    class Meta:
        verbose_name = 'قطعه'
        verbose_name_plural = 'قطعه‌ها'
        constraints = [models.UniqueConstraint(fields=['village_map', 'uid'], name='map_parcel_uid_unique')]

    def __str__(self):
        return self.renewal_code or f'قطعه بدون شماره ({self.pk})'


class ParcelArchive(models.Model):
    """The plot's file: building permit, owner. Empty until staff fill it in."""
    parcel = models.OneToOneField(MapParcel, on_delete=models.CASCADE, related_name='archive')
    permit_number = models.CharField(max_length=60, blank=True, verbose_name='شماره پروانه')
    permit_date = models.DateField(null=True, blank=True, verbose_name='تاریخ پروانه')
    permit_type = models.CharField(max_length=60, blank=True, verbose_name='نوع پروانه')
    permit_notes = models.TextField(blank=True, verbose_name='توضیحات پروانه')
    # عرصه (the land) and اعیان (what stands on it) can belong to different people: the owner_* fields are the land's
    owner_name = models.CharField(max_length=150, blank=True, verbose_name='نام مالک عرصه')
    owner_national_id = models.CharField(max_length=10, blank=True, verbose_name='کد ملی مالک عرصه')
    owner_phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن مالک عرصه')
    building_owner_name = models.CharField(max_length=150, blank=True, verbose_name='نام مالک اعیان')
    building_owner_national_id = models.CharField(max_length=10, blank=True, verbose_name='کد ملی مالک اعیان')
    building_owner_phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن مالک اعیان')
    building_floors = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='تعداد طبقات')
    building_floor_area = models.FloatField(null=True, blank=True, verbose_name='زیربنا (مترمربع)')
    notes = models.TextField(blank=True, verbose_name='یادداشت')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'بایگانی قطعه'
        verbose_name_plural = 'بایگانی قطعه‌ها'


class ParcelFeePayment(models.Model):
    """A fee (عوارض) paid for the plot; money is whole rials."""
    parcel = models.ForeignKey(MapParcel, on_delete=models.CASCADE, related_name='payments')
    fee_type = models.CharField(max_length=80, verbose_name='نوع عوارض')
    fiscal_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='سال')
    amount = models.DecimalField(verbose_name='مبلغ (ریال)', **MONEY)
    paid_on = models.DateField(null=True, blank=True, verbose_name='تاریخ پرداخت')
    receipt_no = models.CharField(max_length=60, blank=True, verbose_name='شماره فیش')
    notes = models.CharField(max_length=300, blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'پرداخت عوارض'
        verbose_name_plural = 'پرداخت‌های عوارض'
        ordering = ['-paid_on', '-id']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='parcel_payment_positive')]


class MapBuilding(models.Model):
    """A building footprint (اعیان) standing on a plot (عرصه)."""
    village_map = models.ForeignKey(VillageMap, on_delete=models.CASCADE, related_name='buildings')
    parcel = models.ForeignKey(MapParcel, null=True, blank=True, on_delete=models.SET_NULL, related_name='buildings')
    area_m2 = models.FloatField(default=0)
    built_year = models.PositiveSmallIntegerField(null=True, blank=True)
    geometry = models.JSONField(verbose_name='هندسه (GeoJSON)')

    class Meta:
        verbose_name = 'اعیان'
        verbose_name_plural = 'اعیان'


class ParcelLock(models.Model):
    """A plot locked against municipal services. Active while ``unlocked_at`` is empty; history is kept."""
    REASONS = [('debt', 'بدهی'), ('neighbor_complaint', 'شکایت همسایه'), ('street_occupation', 'اشغال معبر')]
    parcel = models.ForeignKey(MapParcel, on_delete=models.CASCADE, related_name='locks')
    reason = models.CharField(max_length=20, choices=REASONS, verbose_name='دلیل قفل')
    notes = models.CharField(max_length=500, blank=True, verbose_name='توضیحات')
    locked_at = models.DateTimeField(auto_now_add=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    unlock_notes = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = 'قفل ملک'
        verbose_name_plural = 'قفل‌های ملک'
        ordering = ['-locked_at']
        constraints = [models.UniqueConstraint(fields=['parcel', 'reason'], condition=models.Q(unlocked_at__isnull=True),
                                               name='one_active_lock_per_reason')]

    @property
    def active(self):
        return self.unlocked_at is None
