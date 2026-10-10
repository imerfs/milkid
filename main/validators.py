"""
Custom validators for MelkID application
"""
import os
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import magic  # pip install python-magic-bin


def validate_file_size(file):
    """
    Validate uploaded file size
    """
    max_size = getattr(settings, 'MAX_FILE_SIZE', 10 * 1024 * 1024)  # 10MB default
    
    if file.size > max_size:
        raise ValidationError(
            _('حجم فایل نباید بیشتر از %(max)s مگابایت باشد.'),
            params={'max': max_size / (1024 * 1024)},
        )


def validate_file_extension(file):
    """
    Validate file extension
    """
    allowed_extensions = getattr(
        settings, 
        'ALLOWED_FILE_EXTENSIONS', 
        ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'dwg', 'dxf']
    )
    
    ext = os.path.splitext(file.name)[1][1:].lower()
    
    if ext not in allowed_extensions:
        raise ValidationError(
            _('فرمت فایل مجاز نیست. فرمت‌های مجاز: %(formats)s'),
            params={'formats': ', '.join(allowed_extensions)},
        )


# Types libmagic reports per extension. PDF/JPEG/PNG are detected reliably, so they are strict;
# Office/CAD formats are often reported as generic containers or text, so those are lenient but
# executables (application/x-dosexec, x-executable, ...) never match any of them.
ALLOWED_MIMES = {
    'pdf': {'application/pdf'},
    'jpg': {'image/jpeg'}, 'jpeg': {'image/jpeg'},
    'png': {'image/png'},
    'doc': {'application/msword', 'application/CDFV2', 'application/x-ole-storage', 'application/vnd.ms-office'},
    'docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/zip',
             'application/octet-stream'},
    'dwg': {'image/vnd.dwg', 'application/acad', 'application/x-dwg', 'application/octet-stream'},
    'dxf': {'image/vnd.dxf', 'application/dxf', 'text/plain', 'application/octet-stream'},
}


def validate_file_content(file):
    """
    Validate file content matches its extension (prevents file spoofing)
    """
    ext = os.path.splitext(file.name)[1][1:].lower()
    try:
        file_head = file.read(2048)
        file.seek(0)
        mime = magic.from_buffer(file_head, mime=True)
    except Exception:
        return   # libmagic unavailable or unreadable: the extension and size checks still apply

    if mime not in ALLOWED_MIMES.get(ext, set()):
        raise ValidationError(
            _('محتوای فایل با پسوند آن مطابقت ندارد. فایل ممکن است خطرناک باشد.')
        )


def validate_iranian_national_id(value):
    """
    Validate Iranian National ID (کد ملی)
    """
    if not value or len(value) != 10 or not value.isdigit():
        raise ValidationError(_('کد ملی باید 10 رقم باشد.'))
    
    # Check sum algorithm
    check = int(value[9])
    s = sum(int(value[i]) * (10 - i) for i in range(9)) % 11
    
    if (s < 2 and check == s) or (s >= 2 and check == 11 - s):
        return value
    
    raise ValidationError(_('کد ملی معتبر نیست.'))


def validate_iranian_mobile(value):
    """
    Validate Iranian mobile number
    """
    if not value or len(value) != 11:
        raise ValidationError(_('شماره موبایل باید 11 رقم باشد.'))
    
    if not value.startswith('09'):
        raise ValidationError(_('شماره موبایل باید با 09 شروع شود.'))
    
    if not value.isdigit():
        raise ValidationError(_('شماره موبایل فقط باید شامل اعداد باشد.'))
    
    return value


def validate_property_area(value):
    """
    Validate property area (must be positive and reasonable)
    """
    if value <= 0:
        raise ValidationError(_('مساحت ملک باید بیشتر از صفر باشد.'))
    
    if value > 1000000:  # 1 million square meters
        raise ValidationError(_('مساحت ملک خیلی زیاد است. لطفا مقدار را بررسی کنید.'))
    
    return value


def validate_year(value):
    """
    Validate construction year
    """
    from datetime import datetime
    import jdatetime
    
    current_year = jdatetime.datetime.now().year
    
    if value < 1300:
        raise ValidationError(_('سال ساخت خیلی قدیمی است.'))
    
    if value > current_year + 2:
        raise ValidationError(_('سال ساخت نمی‌تواند در آینده باشد.'))
    
    return value


def validate_price(value):
    """
    Validate price (must be positive and reasonable)
    """
    if value < 0:
        raise ValidationError(_('قیمت نمی‌تواند منفی باشد.'))
    
    if value > 999999999999:  # 1 trillion
        raise ValidationError(_('قیمت خیلی زیاد است.'))
    
    return value
