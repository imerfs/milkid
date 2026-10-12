"""Voucher images (تصاویر اسناد): scans of the paper behind a voucher, kept in private storage per municipality."""
import os

from django.core.exceptions import ValidationError
from django.db import transaction

from main.accounting.ledger import _own, _text, municipality_of
from main.models import DocumentImage, Voucher
from main.office.errors import Invalid
from main.validators import validate_file_content

MAX_BYTES = 5 * 1024 * 1024
EXTENSIONS = ('pdf', 'jpg', 'jpeg', 'png')


def images_for(actor, voucher):
    _own(municipality_of(actor), voucher)
    return voucher.images.all()


def get_image(actor, image_id):
    muni = municipality_of(actor)
    return _own(muni, DocumentImage.objects.filter(pk=image_id).first())


def upload(actor, voucher, file, title):
    muni = municipality_of(actor)
    _own(muni, voucher)
    if file is None:
        raise Invalid('فایل را انتخاب کنید.')
    ext = os.path.splitext(file.name)[1][1:].lower()
    if ext not in EXTENSIONS:
        raise Invalid('فقط فایل PDF یا تصویر (JPG، PNG) پذیرفته می‌شود.')
    if file.size > MAX_BYTES:
        raise Invalid('حجم فایل نباید بیشتر از ۵ مگابایت باشد.')
    try:
        validate_file_content(file)
    except ValidationError:
        raise Invalid('محتوای فایل با پسوند آن مطابقت ندارد.')
    title = _text(title, 'عنوان')[:150]
    with transaction.atomic():
        voucher = Voucher.objects.select_for_update().get(pk=voucher.pk)
        if voucher.deleted_at is not None:
            raise Invalid('سند حذف شده است.')
        return DocumentImage.objects.create(
            municipality=muni, voucher=voucher, title=title, file=file, size=file.size,
            content_type=getattr(file, 'content_type', '')[:60], uploaded_by=actor)


def delete(actor, image):
    muni = municipality_of(actor)
    _own(muni, image)
    if Voucher.objects.get(pk=image.voucher_id).status == 'final':
        raise Invalid('تصاویر سند قطعی حذف نمی‌شود.')
    storage, name = image.file.storage, image.file.name
    image.delete()
    storage.delete(name)
