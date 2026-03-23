from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils import timezone
from .models import CustomUser, Booking, Inquiry
from vendor.models import VendorProfile

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=CustomUser.Role.choices)
    company_name = forms.CharField(required=False, max_length=150)
    owner_full_name = forms.CharField(required=False, max_length=150)
    pan_vat_number = forms.CharField(required=False, max_length=50)
    business_registration_number = forms.CharField(required=False, max_length=100)
    business_registration_certificate = forms.FileField(required=False)
    owner_national_id = forms.CharField(required=False, max_length=100)
    contact_phone = forms.CharField(required=False, max_length=30)
    address = forms.CharField(required=False, max_length=255)

    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
            "role",
            "company_name",
            "owner_full_name",
            "pan_vat_number",
            "business_registration_number",
            "business_registration_certificate",
            "owner_national_id",
            "contact_phone",
            "address",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = [
            (CustomUser.Role.CUSTOMER, 'Customer'),
            (CustomUser.Role.VENDOR, 'Vendor'),
        ]

        self.fields['company_name'].widget.attrs.update({
            'placeholder': 'Company name',
        })
        self.fields['owner_full_name'].widget.attrs.update({
            'placeholder': 'Owner or authorized person full name',
        })
        self.fields['pan_vat_number'].widget.attrs.update({
            'placeholder': 'PAN or VAT number',
        })
        self.fields['business_registration_number'].widget.attrs.update({
            'placeholder': 'Business registration number',
        })
        self.fields['owner_national_id'].widget.attrs.update({
            'placeholder': 'Citizenship or national ID number (optional)',
        })
        self.fields['contact_phone'].widget.attrs.update({
            'placeholder': 'Business phone (optional)',
        })
        self.fields['address'].widget.attrs.update({
            'placeholder': 'Business address (optional)',
        })

        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        company_name = (cleaned_data.get('company_name') or '').strip()
        owner_full_name = (cleaned_data.get('owner_full_name') or '').strip()
        pan_vat_number = (cleaned_data.get('pan_vat_number') or '').strip()
        business_registration_number = (cleaned_data.get('business_registration_number') or '').strip()
        business_registration_certificate = cleaned_data.get('business_registration_certificate')

        if role == CustomUser.Role.VENDOR and not company_name:
            self.add_error('company_name', 'Company name is required for vendor registration.')
        if role == CustomUser.Role.VENDOR and not owner_full_name:
            self.add_error('owner_full_name', 'Owner or authorized person full name is required.')
        if role == CustomUser.Role.VENDOR and not pan_vat_number:
            self.add_error('pan_vat_number', 'PAN or VAT number is required.')
        if role == CustomUser.Role.VENDOR and not business_registration_number:
            self.add_error('business_registration_number', 'Business registration number is required.')
        if role == CustomUser.Role.VENDOR and not business_registration_certificate:
            self.add_error('business_registration_certificate', 'Business registration certificate document is required.')

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = self.cleaned_data['role']

        if commit:
            user.save()
            if user.role == CustomUser.Role.VENDOR:
                profile, created = VendorProfile.objects.update_or_create(
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
                    },
                )
                if created and profile.submitted_at is None:
                    profile.submitted_at = timezone.now()
                    profile.save(update_fields=['submitted_at'])

        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ("travel_date",)
        widgets = {
            "travel_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean_travel_date(self):
        travel_date = self.cleaned_data["travel_date"]
        if travel_date < timezone.localdate():
            raise forms.ValidationError("Please choose today or a future date.")
        return travel_date


class InquiryForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ("full_name", "email", "phone", "message")
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Your full name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Your email"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone (optional)"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Tell us what you need"}),
        }
