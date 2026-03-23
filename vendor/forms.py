from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from app.models import CustomUser
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

        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

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
                    'verification_status': VendorProfile.VerificationStatus.PENDING,
                    'submitted_at': timezone.now(),
                },
            )
            if profile.verified_at is not None:
                profile.verified_at = None
                profile.save(update_fields=['verified_at'])

        return user
