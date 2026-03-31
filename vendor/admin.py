from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.mail import send_mail
from django.template.response import TemplateResponse

from .models import VendorProfile


class RejectVendorsForm(forms.Form):
	_selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
	rejection_reason = forms.CharField(
		label='Rejection reason',
		widget=forms.Textarea(attrs={'rows': 4}),
		help_text='This reason will be stored for each selected vendor.',
	)

	def clean_rejection_reason(self):
		reason = (self.cleaned_data.get('rejection_reason') or '').strip()
		if not reason:
			raise forms.ValidationError('Rejection reason is required.')
		return reason


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
	actions = ('approve_selected_vendors', 'reject_selected_vendors')

	list_display = (
		'company_name',
		'owner_full_name',
		'account_holder_name',
		'masked_mobile_payment_number',
		'pan_vat_number',
		'user',
		'verification_status',
		'is_approved',
		'submitted_at',
		'verified_at',
	)
	list_filter = ('verification_status', 'is_approved', 'submitted_at', 'verified_at', 'created_at')
	search_fields = (
		'company_name',
		'owner_full_name',
		'pan_vat_number',
		'business_registration_number',
		'account_holder_name',
		'mobile_payment_number',
		'user__username',
		'user__email',
		'contact_phone',
	)
	readonly_fields = ('submitted_at', 'verified_at', 'created_at', 'updated_at')
	fieldsets = (
		('Vendor Identity', {
			'fields': ('user', 'company_name', 'owner_full_name', 'owner_national_id', 'contact_phone', 'address'),
		}),
		('Payment Details', {
			'fields': ('account_holder_name', 'mobile_payment_number'),
		}),
		('Business KYC', {
			'fields': ('pan_vat_number', 'business_registration_number', 'business_registration_certificate'),
		}),
		('Verification', {
			'fields': ('verification_status', 'rejection_reason', 'is_approved', 'submitted_at', 'verified_at'),
		}),
		('System', {
			'fields': ('created_at', 'updated_at'),
		}),
	)

	def _send_verification_email(self, profile, is_approved):
		email = (profile.user.email or '').strip()
		if not email:
			return False

		subject = 'TravelMate Vendor Application Update'
		if is_approved:
			message = (
				f'Hello {profile.user.username},\n\n'
				'Your vendor account has been approved by the admin team. '
				'You can now log in and access your vendor dashboard.\n\n'
				'Thank you,\n'
				'TravelMate Team'
			)
		else:
			reason = (profile.rejection_reason or '').strip()
			reason_line = f'Reason: {reason}\n\n' if reason else ''
			message = (
				f'Hello {profile.user.username},\n\n'
				'Your vendor account has been rejected by the admin team.\n\n'
				f'{reason_line}'
				'You can update your details and register again.\n\n'
				'Thank you,\n'
				'TravelMate Team'
			)

		from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or settings.EMAIL_HOST_USER
		send_mail(subject, message, from_email, [email], fail_silently=False)
		return True

	@admin.action(description='Approve selected vendors')
	def approve_selected_vendors(self, request, queryset):
		updated = 0
		emails_sent = 0
		for profile in queryset:
			profile.verification_status = VendorProfile.VerificationStatus.APPROVED
			profile.save()
			updated += 1
			try:
				if self._send_verification_email(profile, is_approved=True):
					emails_sent += 1
			except Exception as exc:
				self.message_user(
					request,
					f'Could not send approval email to {profile.user.email}: {exc}',
					level=messages.ERROR,
				)

		self.message_user(
			request,
			f'{updated} vendor(s) approved successfully. {emails_sent} email(s) sent.',
			level=messages.SUCCESS,
		)

	@admin.action(description='Reject selected vendors (requires reason)')
	def reject_selected_vendors(self, request, queryset):
		if 'apply' in request.POST:
			form = RejectVendorsForm(request.POST)
			if form.is_valid():
				reason = form.cleaned_data['rejection_reason']
				selected_ids = request.POST.getlist('_selected_action')
				target_qs = VendorProfile.objects.filter(pk__in=selected_ids)

				updated = 0
				emails_sent = 0
				for profile in target_qs:
					profile.verification_status = VendorProfile.VerificationStatus.REJECTED
					profile.rejection_reason = reason
					profile.save()
					updated += 1
					try:
						if self._send_verification_email(profile, is_approved=False):
							emails_sent += 1
					except Exception as exc:
						self.message_user(
							request,
							f'Could not send rejection email to {profile.user.email}: {exc}',
							level=messages.ERROR,
						)

				self.message_user(
					request,
					f'{updated} vendor(s) rejected successfully. {emails_sent} email(s) sent.',
					level=messages.WARNING,
				)
				return None
		else:
			form = RejectVendorsForm(
				initial={'_selected_action': request.POST.getlist(ACTION_CHECKBOX_NAME)}
			)

		context = {
			**self.admin_site.each_context(request),
			'opts': self.model._meta,
			'vendors': queryset,
			'form': form,
			'title': 'Reject selected vendors',
		}
		return TemplateResponse(request, 'admin/vendor/reject_selected_vendors.html', context)

	@admin.display(description='eSewa Number')
	def masked_mobile_payment_number(self, obj):
		return obj.masked_mobile_payment_number
