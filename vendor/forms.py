from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory
from django.utils import timezone

from app.models import CustomUser, Destination, HotSale, Inquiry, Package, PackageItinerary
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

        self.fields['is_active'].widget.attrs.pop('class', None)
        self.fields['destination'].queryset = Destination.objects.order_by('name')
        self.fields['destination'].required = True


class PackageItineraryForm(forms.ModelForm):
    class Meta:
        model = PackageItinerary
        fields = ('day_number', 'title', 'description', 'activities')
        widgets = {
            'day_number': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'Day'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Day title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'What happens on this day?'}),
            'activities': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Activities, transfers, highlights'}),
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
        if vendor_profile is not None:
            package_qs = package_qs.filter(vendor=vendor_profile)

        self.fields['package'].queryset = package_qs.order_by('title')


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
