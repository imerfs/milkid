"""Financial settings (تنظیمات مالی): cost centers, standard descriptions and signatories of the municipality."""
from django.db import transaction
from django.db.models import Q

from main.accounting.ledger import _locked, _own, _text, municipality_of
from main.models import Contract, CostCenter, Municipality, Signatory, StandardDescription, VoucherLine
from main.office.errors import Conflict, Invalid


def cost_centers(actor):
    return CostCenter.objects.filter(municipality=municipality_of(actor))


def descriptions(actor):
    return StandardDescription.objects.filter(municipality=municipality_of(actor))


def signatories(actor):
    return Signatory.objects.filter(municipality=municipality_of(actor))


def add_cost_center(actor, code, title):
    muni = municipality_of(actor)
    code, title = _text(code, 'کد')[:10], _text(title, 'شرح')[:100]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if CostCenter.objects.filter(municipality=muni, code=code).exists():
            raise Conflict('این کد قبلاً برای مرکز هزینه دیگری ثبت شده است.')
        return CostCenter.objects.create(municipality=muni, code=code, title=title)


def delete_cost_center(actor, center):
    muni = municipality_of(actor)
    _own(muni, center)
    with transaction.atomic():
        center = _locked(CostCenter, center.pk)
        if VoucherLine.objects.filter(cost_center=center).exists() or Contract.objects.filter(cost_center=center).exists():
            raise Conflict('این مرکز هزینه در اسناد یا قراردادها استفاده شده و حذف نمی‌شود.')
        center.delete()


def add_description(actor, kind, code, text):
    muni = municipality_of(actor)
    if kind not in dict(StandardDescription.KINDS):
        raise Invalid('نوع شرح نامعتبر است.')
    code, text = _text(code, 'کد')[:10], _text(text, 'شرح')[:300]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if StandardDescription.objects.filter(municipality=muni, kind=kind, code=code).exists():
            raise Conflict('این کد قبلاً ثبت شده است.')
        return StandardDescription.objects.create(municipality=muni, kind=kind, code=code, text=text)


def delete_description(actor, obj):
    _own(municipality_of(actor), obj)
    obj.delete()


def add_signatory(actor, name, position):
    muni = municipality_of(actor)
    name, position = _text(name, 'نام')[:150], _text(position, 'سمت')[:100]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if Signatory.objects.filter(municipality=muni).filter(Q(name=name, position=position)).exists():
            raise Conflict('این امضاکننده قبلاً ثبت شده است.')
        return Signatory.objects.create(municipality=muni, name=name, position=position)


def delete_signatory(actor, obj):
    _own(municipality_of(actor), obj)
    obj.delete()
