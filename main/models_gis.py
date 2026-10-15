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
    parcel_count = models.PositiveIntegerField(default=0)
    area_m2 = models.FloatField(default=0)
    geometry = models.JSONField(verbose_name='هندسه (GeoJSON)')

    class Meta:
        verbose_name = 'بلوک'
        verbose_name_plural = 'بلوک‌ها'
        constraints = [models.UniqueConstraint(fields=['village_map', 'number'], name='map_block_unique')]

    def __str__(self):
        return f'بلوک {self.number}'


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
    owner_name = models.CharField(max_length=150, blank=True, verbose_name='نام مالک')
    owner_national_id = models.CharField(max_length=10, blank=True, verbose_name='کد ملی مالک')
    owner_phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن مالک')
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
