"""
Custom widgets for Persian/Jalali date handling
"""
from django import forms
from django.forms.widgets import DateInput, DateTimeInput
import jdatetime
from datetime import datetime, date


class JalaliDateInput(DateInput):
    """
    Persian/Jalali Date Input Widget
    """
    input_type = 'text'
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {
            'class': 'form-control jalali-date',
            'placeholder': 'مثال: 1403/08/15',
            'dir': 'ltr',
            'autocomplete': 'off'
        }
        if attrs:
            default_attrs.update(attrs)
        
        super().__init__(attrs=default_attrs, format=format)
    
    def format_value(self, value):
        """Convert Gregorian date to Jalali for display"""
        if value is None:
            return ''
        
        if isinstance(value, str):
            try:
                # Try to parse as Gregorian date first
                value = datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return value
        
        if isinstance(value, (date, datetime)):
            if isinstance(value, datetime):
                value = value.date()
            
            # Convert to Jalali
            jalali_date = jdatetime.date.fromgregorian(date=value)
            return jalali_date.strftime('%Y/%m/%d')
        
        return value
    
    def value_from_datadict(self, data, files, name):
        """Convert Jalali date input to Gregorian for storage"""
        value = data.get(name)
        if not value:
            return None
        
        try:
            # Parse Jalali date
            if '/' in value:
                parts = value.split('/')
                if len(parts) == 3:
                    year, month, day = map(int, parts)
                    # Create Jalali date and convert to Gregorian
                    jalali_date = jdatetime.date(year, month, day)
                    gregorian_date = jalali_date.togregorian()
                    return gregorian_date.strftime('%Y-%m-%d')
            
            return value
        except (ValueError, TypeError):
            return value


class JalaliDateTimeInput(DateTimeInput):
    """
    Persian/Jalali DateTime Input Widget
    """
    input_type = 'text'
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {
            'class': 'form-control jalali-datetime',
            'placeholder': 'مثال: 1403/08/15 14:30',
            'dir': 'ltr',
            'autocomplete': 'off'
        }
        if attrs:
            default_attrs.update(attrs)
        
        super().__init__(attrs=default_attrs, format=format)
    
    def format_value(self, value):
        """Convert Gregorian datetime to Jalali for display"""
        if value is None:
            return ''
        
        if isinstance(value, str):
            try:
                # Try to parse as Gregorian datetime first
                if 'T' in value:
                    value = datetime.fromisoformat(value.replace('T', ' '))
                else:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return value
        
        if isinstance(value, datetime):
            # Convert to Jalali
            jalali_datetime = jdatetime.datetime.fromgregorian(datetime=value)
            return jalali_datetime.strftime('%Y/%m/%d %H:%M')
        
        return value
    
    def value_from_datadict(self, data, files, name):
        """Convert Jalali datetime input to Gregorian for storage"""
        value = data.get(name)
        if not value:
            return None
        
        try:
            # Parse Jalali datetime
            if '/' in value:
                if ' ' in value:
                    date_part, time_part = value.split(' ', 1)
                    date_parts = date_part.split('/')
                    
                    if len(date_parts) == 3:
                        year, month, day = map(int, date_parts)
                        
                        # Parse time
                        if ':' in time_part:
                            time_parts = time_part.split(':')
                            hour = int(time_parts[0])
                            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                            second = int(time_parts[2]) if len(time_parts) > 2 else 0
                        else:
                            hour = minute = second = 0
                        
                        # Create Jalali datetime and convert to Gregorian
                        jalali_datetime = jdatetime.datetime(year, month, day, hour, minute, second)
                        gregorian_datetime = jalali_datetime.togregorian()
                        return gregorian_datetime.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    # Only date provided
                    date_parts = value.split('/')
                    if len(date_parts) == 3:
                        year, month, day = map(int, date_parts)
                        jalali_date = jdatetime.date(year, month, day)
                        gregorian_date = jalali_date.togregorian()
                        return gregorian_date.strftime('%Y-%m-%d 00:00:00')
            
            return value
        except (ValueError, TypeError):
            return value


class JalaliDateField(forms.DateField):
    """
    Persian/Jalali Date Field
    """
    widget = JalaliDateInput
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', 'تاریخ را به صورت شمسی وارد کنید (مثال: 1403/08/15)')
        super().__init__(*args, **kwargs)


class JalaliDateTimeField(forms.DateTimeField):
    """
    Persian/Jalali DateTime Field
    """
    widget = JalaliDateTimeInput
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', 'تاریخ و زمان را به صورت شمسی وارد کنید (مثال: 1403/08/15 14:30)')
        super().__init__(*args, **kwargs)