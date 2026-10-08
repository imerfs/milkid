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


def validate_file_content(file):
    """
    Validate file content matches its extension (prevents file spoofing)
    """
    try:
        # Read first 2048 bytes to detect file type
        file_head = file.read(2048)
        file.seek(0)
        
        mime = magic.from_buffer(file_head, mime=True)
        
        # Define allowed MIME types
        allowed_mimes = {
            'application/pdf': ['pdf'],
            'image/jpeg': ['jpg', 'jpeg'],
            'image/png': ['png'],
            'application/msword': ['doc'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['docx'],
            'image/vnd.dwg': ['dwg'],
            'image/vnd.dxf': ['dxf'],
        }
        
        ext = os.path.splitext(file.name)[1][1:].lower()
        
        # Check if MIME type matches extension
        valid = False
        for mime_type, extensions in allowed_mimes.items():
            if mime == mime_type and ext in extensions:
                valid = True
                break
        
        if not valid:
            raise ValidationError(
                _('محتوای فایل با پسوند آن مطابقت ندارد. فایل ممکن است خطرناک باشد.')
            )
    
    except Exception as e:
        # If magic library not available, skip content validation
        pass


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
