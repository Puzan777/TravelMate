from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.utils import timezone
from .models import CustomUser, Booking, Inquiry

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = CustomUser.Role.CUSTOMER

        if commit:
            user.save()

        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    def clean_username(self):
        identifier = (self.cleaned_data.get("username") or "").strip()
        if "@" in identifier:
            user = CustomUser.objects.filter(email__iexact=identifier).first()
            if user:
                return user.username
        return identifier


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = (
            "full_name",
            "email",
            "phone",
            "travel_date",
            "number_of_people",
            "pickup_location",
            "nationality",
            "emergency_contact",
        )
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Traveler full name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Traveler email"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone number"}),
            "travel_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "number_of_people": forms.NumberInput(attrs={"class": "form-control", "min": "1", "placeholder": "Number of travelers"}),
            "pickup_location": forms.TextInput(attrs={"class": "form-control", "placeholder": "Pickup location or departure city"}),
            "nationality": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nationality"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control", "placeholder": "Emergency contact"}),
        }

    def clean_travel_date(self):
        travel_date = self.cleaned_data["travel_date"]
        if travel_date < timezone.localdate():
            raise forms.ValidationError("Please choose today or a future date.")
        return travel_date

    def clean_number_of_people(self):
        number_of_people = self.cleaned_data["number_of_people"]
        if number_of_people < 1:
            raise forms.ValidationError("At least one traveler is required.")
        return number_of_people


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
