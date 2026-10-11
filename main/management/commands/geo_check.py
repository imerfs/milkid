"""Read-only health check of the geographic tables (provinces -> counties -> districts -> settlements).

Usage:  python manage.py geo_check

Prints what is wrong and exits with status 1 when a hard problem exists (orphans, mixed-up hierarchy);
softer findings (spelling variants, missing villages) are reported but do not fail the run.
"""
import collections

from django.core.management.base import BaseCommand
from django.db.models import Count

from main.geography import norm  # noqa: F401  (geo_dedupe imports it from here)
from main.models import CityVillage, County, Dehestan, District, Municipality, Province, PropertyAdvertisement, UserProfile

IRAN_PROVINCES = 31


def spelling_variants(model, parent_field):
    seen = collections.defaultdict(set)
    for obj in model.objects.only('name', parent_field):
        seen[(getattr(obj, parent_field), norm(obj.name))].add(obj.name)
    return [sorted(names) for names in seen.values() if len(names) > 1]


def collect():
    """Return (hard problems, soft findings, figures) as plain data so tests can assert on it."""
    hard, soft = [], []
    figures = {m.__name__.lower(): m.objects.count() for m in (Province, County, District, Dehestan, CityVillage)}

    if figures['province'] != IRAN_PROVINCES:
        hard.append(f"{figures['province']} provinces (Iran has {IRAN_PROVINCES})")

    orphans = {
        'provinces without counties': Province.objects.annotate(n=Count('counties')).filter(n=0).count(),
        'counties without districts': County.objects.annotate(n=Count('districts')).filter(n=0).count(),
        'districts without settlements': District.objects.annotate(n=Count('settlements')).filter(n=0).count(),
        'settlements whose dehestan belongs to another district': sum(
            1 for s in CityVillage.objects.select_related('dehestan').exclude(dehestan=None)
            if s.dehestan.district_id != s.district_id),
    }
    hard += [f'{label}: {n}' for label, n in orphans.items() if n]

    for label, model, parent in (('counties', County, 'province_id'), ('districts', District, 'county_id'),
                                 ('settlements', CityVillage, 'district_id')):
        variants = spelling_variants(model, parent)
        if variants:
            soft.append(f'{len(variants)} {label} spelled two ways in the same parent, e.g. {variants[:3]}')

    villages = CityVillage.objects.filter(settlement_type='village').count()
    figures['villages'] = villages
    if villages < figures['district']:
        soft.append(f'only {villages} villages exist (dehyari accounts need their village); '
                    f"{figures['dehestan']} dehestans are loaded but no settlement points to one")
    if CityVillage.objects.exclude(dehestan=None).count() == 0 and figures['dehestan']:
        soft.append('no settlement is linked to a dehestan')
    if CityVillage.objects.filter(population=None).count() == figures['cityvillage']:
        soft.append('no settlement has a population')
    flagged = CityVillage.objects.filter(has_municipality=True).count()
    linked = CityVillage.objects.exclude(municipality=None).count()
    if flagged != linked:
        soft.append(f'{flagged} settlements are flagged as having a municipality but {linked} are linked to one')

    for model in (UserProfile, Municipality, PropertyAdvertisement):
        unlinked = model.objects.exclude(province__isnull=True).exclude(province='').filter(province_fk=None).count()
        if unlinked:
            soft.append(f'{unlinked} {model.__name__} rows name a province that matches no geography row')
    return hard, soft, figures


class Command(BaseCommand):
    help = 'Read-only health check of the geographic tables.'

    def handle(self, *args, **options):
        hard, soft, figures = collect()
        self.stdout.write('Rows: ' + ', '.join(f'{k}={v}' for k, v in figures.items()))
        for line in hard:
            self.stdout.write(self.style.ERROR(f'PROBLEM: {line}'))
        for line in soft:
            self.stdout.write(self.style.WARNING(f'note: {line}'))
        if not hard and not soft:
            self.stdout.write(self.style.SUCCESS('Geographic data looks consistent.'))
        if hard:
            raise SystemExit(1)
