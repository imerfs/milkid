import re
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from . import geo_cascade
from .models import UserProfile, ServiceRequest, RequestDocument, Service, ServiceStep, Municipality, Property, PropertyAdvertisement, PropertyImage, Province, County, District, CityVillage
from .widgets import JalaliDateInput, JalaliDateTimeInput, JalaliDateField, JalaliDateTimeField

class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        label='نام و نام خانوادگی',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام خود را وارد کنید',
            'dir': 'rtl'
        })
    )

    email = forms.EmailField(
        label='ایمیل',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com'
        })
    )

    phone = forms.CharField(
        max_length=15,
        label='شماره تماس',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '09123456789',
            'dir': 'ltr'
        })
    )

    message = forms.CharField(
        label='پیام',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'پیام خود را بنویسید...',
            'dir': 'rtl'
        })
    )

class CustomAuthenticationForm(AuthenticationForm):
    """
    Custom login form supporting username or national ID
    """
    username = forms.CharField(
        label='نام کاربری یا کد ملی',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام کاربری یا کد ملی خود را وارد کنید',
            'dir': 'ltr'
        })
    )

    password = forms.CharField(
        label='رمز عبور',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'رمز عبور',
            'dir': 'ltr'
        })
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')

        # Check if it's a national ID (10 digits)
        if username and username.isdigit() and len(username) == 10:
            try:
                # Find user by national ID
                profile = UserProfile.objects.get(national_id=username)
                return profile.user.username
            except UserProfile.DoesNotExist:
                pass

        return username

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            user_candidate = User.objects.filter(username=username).first()
            if user_candidate and user_candidate.check_password(password):
                if not user_candidate.is_active or (hasattr(user_candidate, 'profile') and not user_candidate.profile.is_active):
                    self.is_blocked_user = True
                    raise forms.ValidationError(
                        'دسترسی حساب کاربری شما توسط مدیر سامانه مسدود گردیده است.',
                        code='inactive'
                    )

        return super().clean()

    def confirm_login_allowed(self, user):
        if not user.is_active or (hasattr(user, 'profile') and not user.profile.is_active):
            self.is_blocked_user = True
            raise forms.ValidationError(
                'دسترسی حساب کاربری شما توسط مدیر سامانه مسدود گردیده است.',
                code='inactive'
            )

class CustomUserCreationForm(UserCreationForm):
    """
    Enhanced registration form with Persian fields and role selection
    """
    email = forms.EmailField(
        required=True,
        label='ایمیل',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com'
        })
    )

    first_name = forms.CharField(
        max_length=30,
        required=True,
        label='نام',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام',
            'dir': 'rtl'
        })
    )

    last_name = forms.CharField(
        max_length=30,
        required=True,
        label='نام خانوادگی',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام خانوادگی',
            'dir': 'rtl'
        })
    )

    national_id = forms.CharField(
        max_length=10,
        required=True,
        label='کد ملی',
        validators=[RegexValidator(r'^\d{10}$', 'کد ملی باید 10 رقم باشد')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '1234567890',
            'dir': 'ltr'
        })
    )

    mobile_number = forms.CharField(
        max_length=11,
        required=True,
        label='شماره موبایل',
        validators=[RegexValidator(r'^09\d{9}$', 'شماره موبایل صحیح وارد کنید (مثال: 09123456789)')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '09123456789',
            'dir': 'ltr'
        })
    )
    
    father_name = forms.CharField(
        max_length=100,
        required=False,
        label='نام پدر',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام پدر',
            'dir': 'rtl'
        })
    )

    role = forms.ChoiceField(
        # 'admin' is never self-service: admins are created/promoted by an existing admin only.
        choices=[c for c in UserProfile.USER_ROLES if c[0] != 'admin'],
        required=True,
        label='نوع کاربری',
        initial='citizen',
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        help_text='توجه: نقش‌های مدیریتی نیاز به تایید مدیر سیستم دارند'
    )
    
    # Geographic fields for management roles (dehyari, mayor)
    province = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='استان',
        empty_label='انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_province_role',
            'dir': 'rtl'
        })
    )
    
    county = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='شهرستان',
        empty_label='ابتدا استان را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_county_role',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )
    
    district = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='بخش',
        empty_label='ابتدا شهرستان را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_district_role',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )
    
    dehestan = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='دهستان',
        empty_label='ابتدا بخش را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_dehestan_role',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )
    
    is_village = forms.BooleanField(
        label='در روستا قرار دارد',
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_is_village_role'
        })
    )
    
    city_village = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='شهر/روستا (انتخاب از لیست)',
        empty_label='انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_city_village_role',
            'disabled': 'disabled',
            'dir': 'rtl'
        }),
        help_text='اگر شهر/روستای شما در لیست نیست، فیلد بعدی را پر کنید'
    )
    
    new_city_village_name = forms.CharField(
        max_length=100,
        required=False,
        label='یا نام شهر/روستای جدید',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'اگر در لیست بالا نیست، نام را بنویسید',
            'dir': 'rtl'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        labels = {
            'username': 'نام کاربری',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Province, County, District, Dehestan, CityVillage
        
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'نام کاربری (انگلیسی)',
            'dir': 'ltr'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'رمز عبور',
            'dir': 'ltr'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'تکرار رمز عبور',
            'dir': 'ltr'
        })
        self.fields['password1'].label = 'رمز عبور'
        self.fields['password2'].label = 'تکرار رمز عبور'
        
        geo_cascade.apply_to_form(self, 'role')

    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if UserProfile.objects.filter(national_id=national_id).exists():
            raise forms.ValidationError('این کد ملی قبلاً ثبت شده است.')
        return national_id

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get('mobile_number')
        if UserProfile.objects.filter(mobile_number=mobile).exists():
            raise forms.ValidationError('این شماره موبایل قبلاً ثبت شده است.')
        return mobile

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.national_id = self.cleaned_data['national_id']
            profile.mobile_number = self.cleaned_data['mobile_number']
            profile.father_name = self.cleaned_data.get('father_name', '')
            profile.role = self.cleaned_data['role']
            
            # Save geographic information
            province = self.cleaned_data.get('province')
            county = self.cleaned_data.get('county')
            district = self.cleaned_data.get('district')
            dehestan = self.cleaned_data.get('dehestan')
            is_village = self.cleaned_data.get('is_village', False)
            city_village = self.cleaned_data.get('city_village')
            new_city_village_name = self.cleaned_data.get('new_city_village_name')
            
            if province:
                profile.province = province.name
            if county:
                profile.county = county.name
            if district:
                profile.district = district.name
            if dehestan:
                profile.dehestan_name = dehestan.name
            profile.is_village = is_village
            if city_village:
                profile.city_village = city_village.name
                profile.city_village_name = city_village.name
            elif new_city_village_name:
                profile.city_village = new_city_village_name
                profile.city_village_name = new_city_village_name
            elif district:
                profile.city_village = district.name
                profile.city_village_name = district.name

            # Set approval status and user activity based on role
            if profile.role in ['citizen', 'owner', 'resident']:
                # Ordinary roles are verified automatically
                profile.is_verified = True
                profile.approval_status = 'approved'
                user.is_active = True
            else:
                # Every staff role (dehyari, engineer, inspector, accountant, council, ...)
                # stays inactive until an admin approves it. Previously inspector and
                # accountant were activated immediately, so anyone could self-register
                # into those roles and see/approve payments.
                profile.approval_status = 'pending'
                profile.is_verified = False
                user.is_active = False

            user.save()
            profile.save()

        return user


class CitizenRegistrationForm(UserCreationForm):
    """
    Registration form specifically for citizens - automatically sets role to 'citizen'
    """
    email = forms.EmailField(
        required=False,
        label='ایمیل (اختیاری)',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com',
            'dir': 'ltr'
        })
    )

    first_name = forms.CharField(
        max_length=30,
        required=True,
        label='نام',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام',
            'dir': 'rtl'
        })
    )

    last_name = forms.CharField(
        max_length=30,
        required=True,
        label='نام خانوادگی',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام خانوادگی',
            'dir': 'rtl'
        })
    )

    national_id = forms.CharField(
        max_length=10,
        required=True,
        label='کد ملی',
        validators=[RegexValidator(r'^\d{10}$', 'کد ملی باید دقیقاً 10 رقم باشد')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '1234567890',
            'dir': 'ltr'
        })
    )

    mobile_number = forms.CharField(
        max_length=11,
        required=True,
        label='شماره موبایل',
        validators=[RegexValidator(r'^09\d{9}$', 'شماره موبایل باید با 09 شروع شده و 11 رقم باشد (مثال: 09123456789)')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '09123456789',
            'dir': 'ltr'
        })
    )
    
    father_name = forms.CharField(
        max_length=100,
        required=False,
        label='نام پدر',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام پدر',
            'dir': 'rtl'
        })
    )
    
    # Geographic fields
    province = forms.ModelChoiceField(
        queryset=None,  # Will be populated in __init__
        required=False,
        label='استان',
        empty_label='انتخاب کنید...',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-all bg-white',
            'id': 'id_province_citizen',
            'dir': 'rtl'
        })
    )
    
    county = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='شهرستان',
        empty_label='ابتدا استان را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-all bg-white',
            'id': 'id_county_citizen',
            'dir': 'rtl'
        })
    )
    
    district = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='بخش',
        empty_label='ابتدا شهرستان را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-all bg-white',
            'id': 'id_district_citizen',
            'dir': 'rtl'
        })
    )
    
    city_village = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='شهر / روستا',
        empty_label='ابتدا بخش را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-all bg-white',
            'id': 'id_city_village_citizen',
            'dir': 'rtl'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        labels = {
            'username': 'نام کاربری',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Province, County, District, CityVillage
        
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'نام کاربری (حروف و اعداد انگلیسی)',
            'dir': 'ltr'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'رمز عبور (حداقل 8 کاراکتر)',
            'dir': 'ltr'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'تکرار رمز عبور',
            'dir': 'ltr'
        })
        self.fields['password1'].label = 'رمز عبور'
        self.fields['password2'].label = 'تکرار رمز عبور'
        
        geo_cascade.apply_to_form(self, 'citizen')

    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if national_id and UserProfile.objects.filter(national_id=national_id).exists():
            raise forms.ValidationError('این کد ملی قبلاً در سامانه ثبت شده است.')
        return national_id

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get('mobile_number')
        if mobile and UserProfile.objects.filter(mobile_number=mobile).exists():
            raise forms.ValidationError('این شماره موبایل قبلاً در سامانه ثبت شده است.')
        return mobile

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email') or ''
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')

        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.national_id = self.cleaned_data.get('national_id', '')
            profile.mobile_number = self.cleaned_data.get('mobile_number', '')
            profile.father_name = self.cleaned_data.get('father_name', '')
            
            # Save geographic information
            province = self.cleaned_data.get('province')
            county = self.cleaned_data.get('county')
            district = self.cleaned_data.get('district')
            city_village = self.cleaned_data.get('city_village')
            
            if province:
                profile.province = province.name
            elif city_village and city_village.district and city_village.district.county and city_village.district.county.province:
                profile.province = city_village.district.county.province.name

            if county:
                profile.county = county.name
            elif city_village and city_village.district and city_village.district.county:
                profile.county = city_village.district.county.name

            if district:
                profile.district = district.name
            elif city_village and city_village.district:
                profile.district = city_village.district.name
            
            if city_village:
                profile.city_village = city_village.name
                profile.city_village_name = city_village.name
                profile.is_village = (city_village.settlement_type == 'village')
            elif district:
                profile.city_village = district.name
                profile.city_village_name = district.name

            profile.role = 'citizen'  # Automatically set to citizen
            profile.is_verified = True  # Citizens are automatically verified
            profile.approval_status = 'approved'  # Citizens get auto approval
            user.is_active = True
            user.save()
            profile.save()

        return user

class ServiceRequestForm(forms.ModelForm):
    """
    Enhanced form for creating new service requests with property details
    """
    class Meta:
        model = ServiceRequest
        fields = ['service', 'title', 'description', 'property_address', 'property_area', 'property_usage', 'deed_number', 'parcel_number']
        labels = {
            'service': 'نوع خدمت',
            'title': 'عنوان درخواست',
            'description': 'توضیحات تکمیلی',
            'property_address': 'آدرس ملک',
            'property_area': 'مساحت ملک (متر مربع)',
            'property_usage': 'کاربری ملک',
            'deed_number': 'شماره سند',
            'parcel_number': 'شماره پلاک',
        }
        widgets = {
            'service': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'عنوان مختصری برای درخواست خود وارد کنید',
                'dir': 'rtl'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'توضیحات کامل درخواست خود را بنویسید...',
                'dir': 'rtl'
            }),
            'property_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'آدرس کامل ملک',
                'dir': 'rtl'
            }),
            'property_area': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مساحت به متر مربع',
                'step': '0.01'
            }),
            'property_usage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مسکونی، تجاری، کشاورزی و غیره',
                'dir': 'rtl'
            }),
            'deed_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'شماره سند مالکیت',
                'dir': 'ltr'
            }),
            'parcel_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'شماره پلاک ملک',
                'dir': 'ltr'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter services based on user role
        if user and hasattr(user, 'profile'):
            user_role = user.profile.role
            if user_role == 'resident':
                self.fields['service'].queryset = Service.objects.filter(
                    is_active=True,
                    required_role__in=['resident', user_role]
                )
            else:
                self.fields['service'].queryset = Service.objects.filter(is_active=True)

class ServiceWizardStepForm(forms.Form):
    """
    Dynamic form for service wizard steps
    """
    def __init__(self, service_step, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service_step = service_step

        field_kwargs = {
            'label': service_step.field_label,
            'help_text': service_step.field_help_text,
            'required': service_step.is_required,
        }

        widget_attrs = {'class': 'form-control'}

        if service_step.field_type == 'text':
            widget_attrs.update({'dir': 'rtl', 'placeholder': service_step.field_help_text})
            self.fields[service_step.field_name] = forms.CharField(
                widget=forms.TextInput(attrs=widget_attrs),
                **field_kwargs
            )
        elif service_step.field_type == 'textarea':
            widget_attrs.update({'dir': 'rtl', 'rows': 4, 'placeholder': service_step.field_help_text})
            self.fields[service_step.field_name] = forms.CharField(
                widget=forms.Textarea(attrs=widget_attrs),
                **field_kwargs
            )
        elif service_step.field_type == 'number':
            self.fields[service_step.field_name] = forms.DecimalField(
                widget=forms.NumberInput(attrs=widget_attrs),
                **field_kwargs
            )
        elif service_step.field_type == 'email':
            self.fields[service_step.field_name] = forms.EmailField(
                widget=forms.EmailInput(attrs=widget_attrs),
                **field_kwargs
            )
        elif service_step.field_type == 'file':
            widget_attrs.update({'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'})
            self.fields[service_step.field_name] = forms.FileField(
                widget=forms.FileInput(attrs=widget_attrs),
                **field_kwargs
            )
        elif service_step.field_type == 'select':
            choices = [(choice.strip(), choice.strip()) for choice in service_step.field_choices.split(',')]
            self.fields[service_step.field_name] = forms.ChoiceField(
                choices=[('', 'انتخاب کنید')] + choices,
                widget=forms.Select(attrs=widget_attrs),
                **field_kwargs
            )
        elif service_step.field_type == 'checkbox':
            self.fields[service_step.field_name] = forms.BooleanField(
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                **field_kwargs
            )
        elif service_step.field_type == 'date':
            self.fields[service_step.field_name] = JalaliDateField(
                widget=JalaliDateInput(attrs=widget_attrs),
                **field_kwargs
            )

        # Apply regex validation if provided
        if service_step.validation_regex and service_step.field_type in ['text', 'textarea']:
            self.fields[service_step.field_name].validators.append(
                RegexValidator(service_step.validation_regex, f'فرمت {service_step.field_label} صحیح نیست')
            )

class ProfileUpdateForm(forms.ModelForm):
    """
    Form for updating user profile information - Enhanced for modern UI
    """
    first_name = forms.CharField(
        max_length=30,
        label='نام',
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'dir': 'rtl',
            'placeholder': 'نام خود را وارد کنید'
        })
    )

    last_name = forms.CharField(
        max_length=30,
        label='نام خانوادگی',
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'dir': 'rtl',
            'placeholder': 'نام خانوادگی خود را وارد کنید'
        })
    )

    email = forms.EmailField(
        label='ایمیل',
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@domain.com'
        })
    )

    mobile_number = forms.CharField(
        max_length=11,
        label='شماره موبایل',
        required=True,
        validators=[RegexValidator(r'^09\d{9}$', 'شماره موبایل صحیح وارد کنید (مثال: 09123456789)')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'dir': 'ltr',
            'placeholder': '09123456789',
            'maxlength': '11'
        })
    )

    # Geographic fields
    province = forms.ModelChoiceField(
        queryset=None,  # Will be populated in __init__
        required=False,
        label='استان',
        empty_label='انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control form-select',
            'id': 'id_province',
            'dir': 'rtl'
        })
    )

    county = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='شهرستان',
        empty_label='ابتدا استان را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control form-select',
            'id': 'id_county',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )

    district = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='بخش',
        empty_label='ابتدا شهرستان را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control form-select',
            'id': 'id_district',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )

    dehestan = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='دهستان',
        empty_label='ابتدا بخش را انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control form-select',
            'id': 'id_dehestan',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )
    
    is_village = forms.BooleanField(
        label='در روستا قرار دارد',
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_is_village'
        })
    )
    
    city_village = forms.ModelChoiceField(
        queryset=None,  # Will be populated dynamically
        required=False,
        label='شهر/روستا',
        empty_label='انتخاب کنید',
        widget=forms.Select(attrs={
            'class': 'form-control form-select',
            'id': 'id_city_village',
            'disabled': 'disabled',
            'dir': 'rtl'
        })
    )

    class Meta:
        model = UserProfile
        fields = ['mobile_number', 'is_village']
        # Note: province, county, district, dehestan, city_village are custom ModelChoiceFields
        # They are not part of the model directly, so we handle them manually in save()

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Store user for later use in save
        self.user = user
        from .models import Province, County, District, Dehestan, CityVillage
        
        # Set initial values for User model fields
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
        
        # ALWAYS show all provinces - never filter this
        self.fields['province'].queryset = Province.objects.all().order_by('name')
        
        # Initialize other dropdowns as empty by default (or all if bound)
        if self.is_bound:
            self.fields['county'].queryset = County.objects.all()
            self.fields['district'].queryset = District.objects.all()
            self.fields['dehestan'].queryset = Dehestan.objects.all()
            self.fields['city_village'].queryset = CityVillage.objects.all()
        else:
            self.fields['county'].queryset = County.objects.none()
            self.fields['district'].queryset = District.objects.none()
            self.fields['dehestan'].queryset = Dehestan.objects.none()
            self.fields['city_village'].queryset = CityVillage.objects.none()
        
        # If instance has existing geographic data, populate dependent dropdowns
        if self.instance and self.instance.pk:
            profile = self.instance
            
            # Try to find and set province
            if profile.province:
                try:
                    province_obj = Province.objects.get(name=profile.province)
                    self.fields['province'].initial = province_obj
                    # Enable and populate county dropdown with ALL counties of selected province
                    self.fields['county'].queryset = County.objects.filter(province=province_obj).order_by('name')
                    self.fields['county'].widget.attrs.pop('disabled', None)
                    
                    # Try to find and set county
                    if profile.county:
                        try:
                            county_obj = County.objects.get(name=profile.county, province=province_obj)
                            self.fields['county'].initial = county_obj
                            # Enable and populate district dropdown
                            self.fields['district'].queryset = District.objects.filter(county=county_obj).order_by('name')
                            self.fields['district'].widget.attrs.pop('disabled', None)
                            
                            # Try to find and set district
                            if profile.district:
                                try:
                                    district_obj = District.objects.get(name=profile.district, county=county_obj)
                                    self.fields['district'].initial = district_obj
                                    # Enable and populate dehestan dropdown
                                    self.fields['dehestan'].queryset = Dehestan.objects.filter(district=district_obj).order_by('name')
                                    self.fields['dehestan'].widget.attrs.pop('disabled', None)
                                    
                                    # Try to find and set dehestan
                                    if profile.dehestan_name:
                                        try:
                                            dehestan_obj = Dehestan.objects.get(name=profile.dehestan_name, district=district_obj)
                                            self.fields['dehestan'].initial = dehestan_obj
                                            # Enable and populate city/village dropdown
                                            self.fields['city_village'].queryset = CityVillage.objects.filter(dehestan=dehestan_obj).order_by('name')
                                            self.fields['city_village'].widget.attrs.pop('disabled', None)
                                        except Dehestan.DoesNotExist:
                                            pass
                                    else:
                                        # If no dehestan, show cities/villages in the district
                                        self.fields['city_village'].queryset = CityVillage.objects.filter(district=district_obj, dehestan__isnull=True).order_by('name')
                                        self.fields['city_village'].widget.attrs.pop('disabled', None)
                                    
                                    # Try to find and set city/village
                                    if profile.city_village_name:
                                        try:
                                            city_village_obj = CityVillage.objects.get(name=profile.city_village_name, district=district_obj)
                                            self.fields['city_village'].initial = city_village_obj
                                        except CityVillage.DoesNotExist:
                                            pass
                                except District.DoesNotExist:
                                    pass
                        except County.DoesNotExist:
                            pass
                except Province.DoesNotExist:
                    pass

    def save(self, user=None, commit=True):
        # Get profile instance (but don't save yet)
        profile = super().save(commit=False)
        
        # Use stored user if not provided
        if user is None:
            user = self.user
        
        # Update User model fields
        if user:
            user.first_name = self.cleaned_data.get('first_name', user.first_name)
            user.last_name = self.cleaned_data.get('last_name', user.last_name)
            user.email = self.cleaned_data.get('email', user.email)
        
        # Get geographic data from form (these are custom fields, not in Meta.fields)
        # We need to get them from self.data (POST data) instead of cleaned_data
        province_id = self.data.get('province', '')
        county_id = self.data.get('county', '')
        district_id = self.data.get('district', '')
        dehestan_id = self.data.get('dehestan', '')
        city_village_id = self.data.get('city_village', '')
        
        # Import models
        from .models import Province, County, District, Dehestan, CityVillage
        
        # Update province
        if province_id:
            try:
                province = Province.objects.get(pk=province_id)
                profile.province = province.name
            except Province.DoesNotExist:
                profile.province = ''
        else:
            profile.province = ''
        
        # Update county
        if county_id:
            try:
                county = County.objects.get(pk=county_id)
                profile.county = county.name
            except County.DoesNotExist:
                profile.county = ''
        else:
            profile.county = ''
        
        # Update district
        if district_id:
            try:
                district = District.objects.get(pk=district_id)
                profile.district = district.name
            except District.DoesNotExist:
                profile.district = ''
        else:
            profile.district = ''
        
        # Update dehestan
        if dehestan_id:
            try:
                dehestan = Dehestan.objects.get(pk=dehestan_id)
                profile.dehestan_name = dehestan.name
            except Dehestan.DoesNotExist:
                profile.dehestan_name = ''
        else:
            profile.dehestan_name = ''
        
        # Update city/village
        if city_village_id:
            try:
                city_village = CityVillage.objects.get(pk=city_village_id)
                profile.city_village_name = city_village.name
                profile.city_village = city_village.name  # Also update old field
            except CityVillage.DoesNotExist:
                profile.city_village_name = ''
                profile.city_village = ''
        else:
            profile.city_village_name = ''
            profile.city_village = ''

        if commit:
            if user:
                user.save()
            profile.save()

        return profile

class DocumentUploadForm(forms.ModelForm):
    """
    Form for uploading documents to service requests
    """
    class Meta:
        model = RequestDocument
        fields = ['document', 'document_name']
        labels = {
            'document': 'فایل سند',
            'document_name': 'نام سند',
        }
        widgets = {
            'document': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'
            }),
            'document_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'نام سند را وارد کنید',
                'dir': 'rtl'
            }),
        }

class AnnouncementForm(forms.ModelForm):
    """Form for creating announcements"""

    target_roles = forms.MultipleChoiceField(
        choices=[('all', 'همه کاربران')] + UserProfile.USER_ROLES,
        widget=forms.CheckboxSelectMultiple,
        label='مخاطبین'
    )

    class Meta:
        from .models import Announcement
        model = Announcement
        fields = ['title', 'content', 'priority', 'target_roles', 'expires_at']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'dir': 'rtl'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'expires_at': JalaliDateTimeInput(attrs={'class': 'form-control'}),
        }

class ViolationReportForm(forms.ModelForm):
    """Form for reporting violations"""

    class Meta:
        from .models import ViolationReport
        model = ViolationReport
        fields = ['title', 'description', 'location_address', 'latitude', 'longitude', 'photo']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'rtl'}),
            'location_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'dir': 'rtl'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

class SuggestionForm(forms.ModelForm):
    """Form for suggestions and complaints"""

    class Meta:
        from .models import Suggestion
        model = Suggestion
        fields = ['type', 'subject', 'description']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-control'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'dir': 'rtl'}),
        }

class EventPermitForm(forms.ModelForm):
    """Form for event permit requests"""

    class Meta:
        from .models import EventPermit
        model = EventPermit
        fields = ['event_type', 'event_name', 'location', 'start_date', 'end_date', 
                 'expected_attendees', 'description', 'contact_person', 'contact_phone']
        widgets = {
            'event_type': forms.Select(attrs={'class': 'form-control'}),
            'event_name': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'dir': 'rtl'}),
            'start_date': JalaliDateTimeInput(attrs={'class': 'form-control'}),
            'end_date': JalaliDateTimeInput(attrs={'class': 'form-control'}),
            'expected_attendees': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'rtl'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

class MunicipalityRegistrationForm(forms.ModelForm):
    """
    Form for registering new municipality/rural council with geographic dropdowns
    """
    # Geographic fields as dropdowns
    province = forms.ModelChoiceField(
        queryset=Province.objects.all(),
        empty_label="انتخاب استان",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_province'}),
        label='استان'
    )
    
    county = forms.ModelChoiceField(
        queryset=County.objects.all(),
        empty_label="ابتدا استان را انتخاب کنید",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_county'}),
        label='شهرستان'
    )
    
    district = forms.ModelChoiceField(
        queryset=District.objects.all(),
        empty_label="ابتدا شهرستان را انتخاب کنید",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_district'}),
        label='بخش'
    )
    
    # City/Village as text input (will be created if doesn't exist)
    city_village = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'dir': 'rtl',
            'placeholder': 'نام شهر یا روستا را وارد کنید'
        }),
        label='شهر/روستا',
        help_text='نام شهر یا روستایی که این شهرداری/دهیاری خدمات ارائه می‌دهد'
    )
    
    # Settlement type
    settlement_type = forms.ChoiceField(
        choices=[('city', 'شهر'), ('village', 'روستا')],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='نوع منطقه',
        help_text='آیا این منطقه شهر است یا روستا؟'
    )
    
    manager_password = forms.CharField(
        label='رمز عبور مدیر سیستم',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'رمز عبور برای حساب کاربری مدیر'
        }),
        help_text='این رمز برای ایجاد حساب کاربری مدیر سیستم استفاده خواهد شد'
    )
    
    manager_username = forms.CharField(
        label='نام کاربری مدیر سیستم',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام کاربری منحصر به فرد'
        }),
        help_text='نام کاربری برای دسترسی به پنل مدیریت'
    )
    
    governor_decree = forms.FileField(
        label='حکم فرماندار',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'
        }),
        help_text='فایل حکم انتصاب از فرماندار استان (فرمت‌های مجاز: PDF, JPG, PNG, DOC, DOCX)',
        required=True
    )

    class Meta:
        model = Municipality
        fields = [
            'name', 'municipality_type', 'province', 'county', 'district', 'city_village',
            'official_phone', 'official_email', 'postal_code', 'address',
            'establishment_date', 'population', 'area_hectares',
            'manager_name', 'manager_national_id', 'manager_phone', 'manager_email',
            'license_number'
        ]
        # Note: manager_username, manager_password, governor_decree, province, county, district, settlement_type are custom fields
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'municipality_type': forms.Select(attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'county': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'district': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'official_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'official_email': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ایمیل رسمی'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'dir': 'rtl'}),
            'establishment_date': JalaliDateInput(attrs={'class': 'form-control'}),
            'population': forms.NumberInput(attrs={'class': 'form-control'}),
            'area_hectares': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'manager_name': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'manager_national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'manager_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'manager_email': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ایمیل مدیر'}),
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If this is an update form (instance exists)
        if self.instance and self.instance.pk:
            # Try to populate geographic fields from stored text values
            if hasattr(self.instance, 'province') and self.instance.province:
                try:
                    province_obj = Province.objects.get(name=self.instance.province)
                    self.fields['province'].initial = province_obj
                    self.fields['county'].queryset = County.objects.filter(province=province_obj)
                    
                    if hasattr(self.instance, 'county') and self.instance.county:
                        county_obj = County.objects.get(name=self.instance.county, province=province_obj)
                        self.fields['county'].initial = county_obj
                        self.fields['district'].queryset = District.objects.filter(county=county_obj)
                        
                        if hasattr(self.instance, 'district') and self.instance.district:
                            district_obj = District.objects.get(name=self.instance.district, county=county_obj)
                            self.fields['district'].initial = district_obj
                except (Province.DoesNotExist, County.DoesNotExist, District.DoesNotExist):
                    pass

        geo_cascade.apply_to_form(self, 'municipality')
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate geographic fields
        province = cleaned_data.get('province')
        county = cleaned_data.get('county')
        district = cleaned_data.get('district')
        
        if province and county:
            # Check if county belongs to selected province
            if county.province != province:
                self.add_error('county', 'شهرستان انتخابی متعلق به استان انتخابی نیست.')
        
        if county and district:
            # Check if district belongs to selected county
            if district.county != county:
                self.add_error('district', 'بخش انتخابی متعلق به شهرستان انتخابی نیست.')
        
        # Validate manager fields
        manager_username = cleaned_data.get('manager_username')
        manager_password = cleaned_data.get('manager_password')
        
        if manager_username and User.objects.filter(username=manager_username).exists():
            self.add_error('manager_username', 'این نام کاربری قبلاً استفاده شده است.')
        
        if manager_password:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_password(manager_password)
            except DjangoValidationError as exc:
                for message in exc.messages:
                    self.add_error('manager_password', message)

        return cleaned_data

    def clean_manager_national_id(self):
        national_id = (self.cleaned_data.get('manager_national_id') or '').strip()
        if not (national_id.isdigit() and len(national_id) == 10):
            raise forms.ValidationError('کد ملی باید ۱۰ رقم باشد.')
        if UserProfile.objects.filter(national_id=national_id).exists():
            raise forms.ValidationError('این کد ملی قبلاً ثبت شده است.')
        return national_id

    def clean_manager_phone(self):
        phone = (self.cleaned_data.get('manager_phone') or '').strip()
        if not re.fullmatch(r'09\d{9}', phone):
            raise forms.ValidationError('شماره موبایل صحیح وارد کنید (مثل 09121234567).')
        return phone
    
    def clean_manager_email(self):
        """اعتبارسنجی ایمیل مدیر - فقط بررسی تکراری نبودن"""
        manager_email = self.cleaned_data.get('manager_email')
        
        if manager_email:
            # فقط بررسی تکراری نبودن ایمیل
            if User.objects.filter(email=manager_email).exists():
                raise forms.ValidationError('این آدرس ایمیل قبلاً استفاده شده است.')
        
        return manager_email
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set geographic text fields from selected objects
        if self.cleaned_data.get('province'):
            instance.province = self.cleaned_data['province'].name
        if self.cleaned_data.get('county'):
            instance.county = self.cleaned_data['county'].name
        if self.cleaned_data.get('district'):
            instance.district = self.cleaned_data['district'].name
        
        if commit:
            instance.save()
            
            # Create or get the CityVillage object
            city_village_name = self.cleaned_data.get('city_village')
            settlement_type = self.cleaned_data.get('settlement_type', 'city')
            district_obj = self.cleaned_data.get('district')
            
            if city_village_name and district_obj:
                city_village_obj, created = CityVillage.objects.get_or_create(
                    district=district_obj,
                    name=city_village_name,
                    defaults={
                        'settlement_type': settlement_type,
                        'has_municipality': True,
                        'municipality': instance,
                        'population': instance.population,
                    }
                )
                
                # Update existing record if needed
                if not created:
                    city_village_obj.has_municipality = True
                    city_village_obj.municipality = instance
                    if instance.population:
                        city_village_obj.population = instance.population
                    city_village_obj.save()
        
        return instance

class PropertyAdvertisementForm(forms.ModelForm):
    """
    Form for property advertisement submission
    """

    class Meta:
        model = PropertyAdvertisement
        fields = [
            'ad_type', 'property_type', 'total_area', 'built_area', 
            'floors', 'specific_floor', 'units', 'bedrooms', 'parking', 'construction_year',
            'parking_available', 'storage_room', 'elevator',
            'province', 'county', 'district', 'city_village', 'is_village', 'dehestan',
            'address', 'sale_price', 'rent_price', 'deposit', 'price_negotiable',
            'description', 'contact_name', 'contact_phone'
        ]
        widgets = {
            'ad_type': forms.Select(attrs={'class': 'form-control'}),
            'property_type': forms.Select(attrs={'class': 'form-control'}),
            'total_area': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'built_area': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'floors': forms.NumberInput(attrs={'class': 'form-control'}),
            'specific_floor': forms.NumberInput(attrs={'class': 'form-control'}),
            'units': forms.NumberInput(attrs={'class': 'form-control'}),
            'bedrooms': forms.NumberInput(attrs={'class': 'form-control'}),
            'parking': forms.NumberInput(attrs={'class': 'form-control'}),
            'construction_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'parking_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'storage_room': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'elevator': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'province': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'county': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'district': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'city_village': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'is_village': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dehestan': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'dir': 'rtl'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '1000000'}),
            'rent_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '100000'}),
            'deposit': forms.NumberInput(attrs={'class': 'form-control', 'step': '1000000'}),
            'price_negotiable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'rtl'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_contact_phone(self):
        phone = self.cleaned_data.get('contact_phone')
        if phone and len(phone) != 11:
            raise forms.ValidationError('شماره تلفن باید 11 رقم باشد')
        return phone

    def clean(self):
        cleaned_data = super().clean()
        ad_type = cleaned_data.get('ad_type')
        sale_price = cleaned_data.get('sale_price')
        rent_price = cleaned_data.get('rent_price')

        if ad_type == 'sale' and not sale_price:
            raise forms.ValidationError('برای آگهی فروش، قیمت فروش الزامی است')
        
        if ad_type == 'rent' and not rent_price:
            raise forms.ValidationError('برای آگهی اجاره، اجاره ماهانه الزامی است')
        
        if ad_type == 'both' and not (sale_price and rent_price):
            raise forms.ValidationError('برای آگهی فروش و اجاره، هر دو قیمت الزامی است')

        return cleaned_data

class PropertyRegistrationForm(forms.ModelForm):
    """
    Form for registering new properties in the marketplace
    """
    class Meta:
        model = Property
        fields = [
            'parcel_number', 'deed_number', 'address', 'area', 'usage_type', 'location_area',
            'owner_name', 'owner_national_id', 'owner_phone',
            'construction_year', 'floors', 'units', 'parking_spaces',
            'assessed_value', 'market_price', 'is_for_sale', 'is_for_rent'
        ]
        widgets = {
            'parcel_number': forms.TextInput(attrs={'class': 'form-control'}),
            'deed_number': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'dir': 'rtl'}),
            'area': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'usage_type': forms.Select(attrs={'class': 'form-control'}),
            'location_area': forms.Select(attrs={'class': 'form-control'}),
            'owner_name': forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'}),
            'owner_national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'owner_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'construction_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'floors': forms.NumberInput(attrs={'class': 'form-control'}),
            'units': forms.NumberInput(attrs={'class': 'form-control'}),
            'parking_spaces': forms.NumberInput(attrs={'class': 'form-control'}),
            'assessed_value': forms.NumberInput(attrs={'class': 'form-control'}),
            'market_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_for_sale': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_for_rent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PropertySearchForm(forms.Form):
    """
    Form for searching properties in marketplace
    """
    query = forms.CharField(
        max_length=200,
        required=False,
        label='جستجو',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'جستجو در آدرس، مالک یا شماره پلاک...',
            'dir': 'rtl'
        })
    )
    
    usage_type = forms.ChoiceField(
        choices=[('', 'همه انواع')] + Property.USAGE_TYPES,
        required=False,
        label='نوع کاربری',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    location_area = forms.ChoiceField(
        choices=[('', 'همه مناطق')] + Property.AREAS,
        required=False,
        label='منطقه',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    min_area = forms.DecimalField(
        required=False,
        label='حداقل مساحت',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'متر مربع'
        })
    )
    
    max_area = forms.DecimalField(
        required=False,
        label='حداکثر مساحت',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'متر مربع'
        })
    )
    
    min_price = forms.DecimalField(
        required=False,
        label='حداقل قیمت',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'تومان'
        })
    )
    
    max_price = forms.DecimalField(
        required=False,
        label='حداکثر قیمت',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'تومان'
        })
    )
    
    for_sale = forms.BooleanField(
        required=False,
        label='فروشی',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    for_rent = forms.BooleanField(
        required=False,
        label='اجاره‌ای',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

class ConstructionPermitForm(forms.ModelForm):
    """
    Specialized form for construction permit requests with geographic dropdowns
    """
    class Meta:
        model = ServiceRequest
        fields = [
            'title', 'description', 'province', 'county', 'district', 'city_village',
            'property_address', 'property_area', 'property_usage', 'deed_number', 'parcel_number'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'value': 'درخواست پروانه ساختمان',
                'readonly': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'توضیحات پروژه ساختمانی، نوع ساختمان و مشخصات فنی...',
                'dir': 'rtl'
            }),
            'province': forms.Select(attrs={'class': 'form-control geographic-select', 'id': 'id_province'}),
            'county': forms.Select(attrs={'class': 'form-control geographic-select', 'id': 'id_county', 'disabled': True}),
            'district': forms.Select(attrs={'class': 'form-control geographic-select', 'id': 'id_district', 'disabled': True}),
            'city_village': forms.Select(attrs={'class': 'form-control geographic-select', 'id': 'id_city_village', 'disabled': True}),
            'property_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'آدرس دقیق (پلاک، کوچه، جزئیات بیشتر...)',
                'dir': 'rtl'
            }),
            'property_area': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مساحت ملک به متر مربع'
            }),
            'property_usage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مسکونی، تجاری، صنعتی و غیره',
                'dir': 'rtl'
            }),
            'deed_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'شماره سند مالکیت'
            }),
            'parcel_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'شماره پلاک ثبتی'
            }),
        }
