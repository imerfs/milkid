"""Merge places that are spelled two ways inside the same parent (half-space vs space, Arabic vs Persian letters).

Usage:  python manage.py geo_dedupe            # dry run: prints what would be merged
        python manage.py geo_dedupe --apply    # does it, all or nothing

Everything that pointed at the removed spelling (profiles, municipalities, requests, ads) is repointed
to the kept one; children with the same name are merged recursively, the rest are moved over.
The kept spelling is the one with more references, then the one with a half-space, then the older row.
"""
import collections

from django.core.management.base import BaseCommand
from django.db import transaction

from main.management.commands.geo_check import norm
from main.models import CityVillage, County, Dehestan, District, Municipality, UserProfile

# model -> (field that points at its parent, child models and the field on them that points back)
LEVELS = (
    (County, 'province_id'),
    (District, 'county_id'),
    (Dehestan, 'district_id'),
    (CityVillage, 'district_id'),
)
CHILDREN = {County: [(District, 'county')], District: [(CityVillage, 'district'), (Dehestan, 'district')]}


def references(obj):
    total = 0
    for rel in type(obj)._meta.related_objects:
        total += rel.related_model.objects.filter(**{rel.field.name: obj}).count()
    return total


def groups(model, parent_field):
    seen = collections.defaultdict(list)
    for obj in model.objects.all():
        seen[(getattr(obj, parent_field), norm(obj.name))].append(obj)
    return [objs for objs in seen.values() if len(objs) > 1]


def pick_kept(objs):
    return sorted(objs, key=lambda o: (-references(o), '‌' not in o.name, o.pk))[0]


TEXT_FIELD = {County: 'county', District: 'district', CityVillage: 'city_village'}


def ancestor_names(obj):
    """Names of the parents, as profiles and municipalities store them (plain text columns)."""
    if isinstance(obj, County):
        return {'province': obj.province.name}
    if isinstance(obj, District):
        return {'province': obj.county.province.name, 'county': obj.county.name}
    if isinstance(obj, CityVillage):
        d = obj.district
        return {'province': d.county.province.name, 'county': d.county.name, 'district': d.name}
    return None


def rewrite_text(keep, drop):
    """UserProfile and Municipality keep the place as names, not keys: point them at the kept spelling."""
    column, parents = TEXT_FIELD.get(type(keep)), ancestor_names(keep)
    if column is None:
        return
    for model in (UserProfile, Municipality):
        model.objects.filter(**parents, **{column: drop.name}).update(**{column: keep.name})


def merge(keep, drop):
    """Move everything from ``drop`` into ``keep`` and delete ``drop``."""
    rewrite_text(keep, drop)
    child_models = {m: field for m, field in CHILDREN.get(type(keep), [])}
    for rel in type(keep)._meta.related_objects:
        related, field = rel.related_model, rel.field.name
        if related in child_models:
            kept_children = {norm(c.name): c for c in related.objects.filter(**{field: keep})}
            for child in related.objects.filter(**{field: drop}):
                twin = kept_children.get(norm(child.name))
                if twin:
                    merge(twin, child)
                else:
                    setattr(child, field, keep)
                    child.save()
        else:
            related.objects.filter(**{field: drop}).update(**{field: keep})
    drop.delete()


def plan():
    """List of (kept, [dropped...]) over every level, parents first."""
    result = []
    for model, parent_field in LEVELS:
        for objs in groups(model, parent_field):
            keep = pick_kept(objs)
            result.append((keep, [o for o in objs if o.pk != keep.pk]))
    return result


class Command(BaseCommand):
    help = 'Merge geographic names spelled two ways in the same parent (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='perform the merge')

    def handle(self, *args, **options):
        todo = plan()
        if not todo:
            self.stdout.write(self.style.SUCCESS('No duplicate spellings.'))
            return
        for keep, drops in todo:
            self.stdout.write(f'{type(keep).__name__}: keep "{keep.name}" (#{keep.pk}), merge {[d.name for d in drops]}')
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Dry run. Add --apply to merge.'))
            return
        merged = 0
        with transaction.atomic():
            while True:                    # re-plan after each group: merging a parent changes its children
                todo = plan()
                if not todo:
                    break
                keep, drops = todo[0]
                for drop in drops:
                    merge(keep, drop)
                    merged += 1
        self.stdout.write(self.style.SUCCESS(f'Merged {merged} duplicate rows.'))
