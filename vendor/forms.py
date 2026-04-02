from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory
from django.utils import timezone

from app.models import Activity, ActivityCategory, CustomUser, Destination, HotSale, Inquiry, Package, PackageItinerary
from .models import VendorProfile


class VendorRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    company_name = forms.CharField(required=True, max_length=150)
    owner_full_name = forms.CharField(required=True, max_length=150)
    pan_vat_number = forms.CharField(required=True, max_length=50)
    business_registration_number = forms.CharField(required=True, max_length=100)
    business_registration_certificate = forms.FileField(required=True)
    owner_national_id = forms.CharField(required=False, max_length=100)
    contact_phone = forms.CharField(required=False, max_length=30)
    address = forms.CharField(required=False, max_length=255)
    account_holder_name = forms.CharField(required=True, max_length=150)
    mobile_payment_number = forms.CharField(required=True, max_length=20)

    class Meta:
        model = CustomUser
        fields = (
            'username',
            'email',
            'company_name',
            'owner_full_name',
            'pan_vat_number',
            'business_registration_number',
            'business_registration_certificate',
            'owner_national_id',
            'contact_phone',
            'address',
            'account_holder_name',
            'mobile_payment_number',
            'password1',
            'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_name'].widget.attrs.update({'placeholder': 'Company name'})
        self.fields['owner_full_name'].widget.attrs.update({'placeholder': 'Owner or authorized person full name'})
        self.fields['pan_vat_number'].widget.attrs.update({'placeholder': 'PAN or VAT number'})
        self.fields['business_registration_number'].widget.attrs.update({'placeholder': 'Business registration number'})
        self.fields['owner_national_id'].widget.attrs.update({'placeholder': 'Citizenship or national ID number (optional)'})
        self.fields['contact_phone'].widget.attrs.update({'placeholder': 'Business phone (optional)'})
        self.fields['address'].widget.attrs.update({'placeholder': 'Business address (optional)'})
        self.fields['account_holder_name'].widget.attrs.update({'placeholder': 'Account holder name'})
        self.fields['mobile_payment_number'].widget.attrs.update({'placeholder': 'eSewa number'})

        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = CustomUser.Role.VENDOR

        if commit:
            user.save()
            profile, _ = VendorProfile.objects.update_or_create(
                user=user,
                defaults={
                    'company_name': self.cleaned_data['company_name'].strip(),
                    'owner_full_name': self.cleaned_data['owner_full_name'].strip(),
                    'pan_vat_number': self.cleaned_data['pan_vat_number'].strip(),
                    'business_registration_number': self.cleaned_data['business_registration_number'].strip(),
                    'business_registration_certificate': self.cleaned_data.get('business_registration_certificate'),
                    'owner_national_id': (self.cleaned_data.get('owner_national_id') or '').strip(),
                    'contact_phone': (self.cleaned_data.get('contact_phone') or '').strip(),
                    'address': (self.cleaned_data.get('address') or '').strip(),
                    'account_holder_name': (self.cleaned_data.get('account_holder_name') or '').strip(),
                    'mobile_payment_number': (self.cleaned_data.get('mobile_payment_number') or '').strip(),
                    'verification_status': VendorProfile.VerificationStatus.PENDING,
                    'submitted_at': timezone.now(),
                },
            )
            if profile.verified_at is not None:
                profile.verified_at = None
                profile.save(update_fields=['verified_at'])

        return user


class VendorPackageForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = (
            'title',
            'category',
            'image',
            'price',
            'description',
            'destination',
            'region',
            'city',
            'best_season',
            'duration',
            'max_people',
            'trip_difficulty',
            'activity',
            'max_elevation',
            'accommodation',
            'meal',
            'vehicle',
            'major_highlights',
            'is_active',
        )

    def __init__(self, *args, vendor_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

        self.fields['image'].required = False
        self.fields['is_active'].widget.attrs.pop('class', None)
        self.fields['destination'].queryset = Destination.objects.order_by('name')
        self.fields['destination'].required = True


class PackageItineraryForm(forms.ModelForm):
    class Meta:
        model = PackageItinerary
        fields = (
            'day_number',
            'title',
            'description',
            'activities',
            'max_elevation',
            'duration',
            'distance',
            'difficulty_level',
            'meals_included',
        )
        widgets = {
            'day_number': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'Day'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Day title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'What happens on this day?'}),
            'activities': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Activities, transfers, highlights'}),
            'max_elevation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Max. elevation (optional)'}),
            'duration': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Duration (optional)'}),
            'distance': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Distance (optional)'}),
            'difficulty_level': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Difficulty level (optional)'}),
            'meals_included': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Meals included (optional)'}),
        }


PackageItineraryFormSet = inlineformset_factory(
    Package,
    PackageItinerary,
    form=PackageItineraryForm,
    extra=0,
    can_delete=True,
)


class VendorHotSaleForm(forms.ModelForm):
    class Meta:
        model = HotSale
        fields = (
            'package',
            'activity',
            'sale_price',
            'note',
            'is_active',
        )

    def __init__(self, *args, vendor_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

        self.fields['is_active'].widget.attrs.pop('class', None)

        package_qs = Package.objects.filter(is_active=True)
        activity_qs = Activity.objects.filter(is_active=True)
        if vendor_profile is not None:
            package_qs = package_qs.filter(vendor=vendor_profile)
            activity_qs = activity_qs.filter(vendor=vendor_profile)

        self.fields['package'].queryset = package_qs.order_by('title')
        self.fields['activity'].queryset = activity_qs.order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        package = cleaned_data.get('package')
        activity = cleaned_data.get('activity')

        if bool(package) == bool(activity):
            raise forms.ValidationError('Please choose either a package or an activity.')

        return cleaned_data


class VendorActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = (
            'category',
            'name',
            'description',
            'price',
            'max_group_size',
            'equipment_provided',
            'safety_notes',
            'duration',
            'difficulty_level',
            'min_age',
            'max_weight',
            'min_weight',
            'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Activity description'}),
            'equipment_provided': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'What equipment/items are included?'}),
            'safety_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any warnings or special instructions'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == 'is_active':
                field.widget.attrs.pop('class', None)
                continue
            field.widget.attrs.setdefault('class', 'form-control')

        self.fields['category'].queryset = ActivityCategory.objects.filter(is_active=True).order_by('name')

    def clean_name(self):
        return (self.cleaned_data.get('name') or '').strip()

    def clean_duration(self):
        return (self.cleaned_data.get('duration') or '').strip()

    def clean(self):
        cleaned_data = super().clean()
        min_weight = cleaned_data.get('min_weight')
        max_weight = cleaned_data.get('max_weight')
        max_group_size = cleaned_data.get('max_group_size')
        if min_weight is not None and max_weight is not None and min_weight > max_weight:
            self.add_error('min_weight', 'Minimum weight cannot be greater than maximum weight.')
        if max_group_size is not None and max_group_size <= 0:
            self.add_error('max_group_size', 'Max group size must be greater than 0.')
        return cleaned_data


class VendorInquiryReplyForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ('admin_reply',)
        widgets = {
            'admin_reply': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['admin_reply'].widget.attrs['class'] = 'form-control'
        self.fields['admin_reply'].label = 'Reply to customer'
