from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

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


class DeactivateVendorsForm(forms.Form):
	_selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
	reason = forms.CharField(
		label='Deactivation reason',
		widget=forms.Textarea(attrs={'rows': 4}),
		help_text='This reason will be stored for each selected vendor.',
	)

	def clean_reason(self):
		reason = (self.cleaned_data.get('reason') or '').strip()
		if not reason:
			raise forms.ValidationError('Deactivation reason is required.')
		return reason


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
	change_form_template = 'admin/vendor/vendorprofile/change_form.html'

	actions = (
		'approve_selected_vendors',
		'reject_selected_vendors',
		'deactivate_selected_vendors',
		'reactivate_selected_vendors',
	)

	list_display = (
		'vendor_identity',
		'business_contact',
		'account_state',
		'registered_on',
		'view_details',
	)
	list_display_links = None
	list_per_page = 10
	list_filter = ('verification_status', 'account_status')
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
	readonly_fields = (
		'identity_panel',
		'payment_panel',
		'verification_panel',
		'timeline_panel',
		'business_context_panel',
		'business_certificate_preview',
	)
	fieldsets = (
		('Vendor Profile', {
			'fields': ('identity_panel',),
		}),
		('Payment and Tax', {
			'fields': ('payment_panel',),
		}),
		('Verification', {
			'fields': ('verification_panel',),
		}),
		('Timeline', {
			'fields': ('timeline_panel',),
		}),
		('Business Context', {
			'fields': ('business_context_panel', 'business_certificate_preview'),
		}),
	)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return request.user.is_active and request.user.is_staff and obj is None

	def has_delete_permission(self, request, obj=None):
		return False

	def has_view_permission(self, request, obj=None):
		return request.user.is_active and request.user.is_staff

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<path:object_id>/approve/',
				self.admin_site.admin_view(self.approve_vendor_view),
				name='vendor_vendorprofile_approve',
			),
			path(
				'<path:object_id>/reject/',
				self.admin_site.admin_view(self.reject_vendor_view),
				name='vendor_vendorprofile_reject',
			),
		]
		return custom_urls + urls

	def change_view(self, request, object_id, form_url='', extra_context=None):
		extra_context = extra_context or {}
		obj = self.get_object(request, object_id)
		if obj:
			is_pending = obj.verification_status == VendorProfile.VerificationStatus.PENDING
			extra_context.update({
				'vendor_is_pending': is_pending,
				'approve_url': reverse('admin:vendor_vendorprofile_approve', args=[obj.pk]),
				'reject_url': reverse('admin:vendor_vendorprofile_reject', args=[obj.pk]),
				'back_to_pending_url': f"{reverse('admin:vendor_vendorprofile_changelist')}?verification_status__exact=PENDING",
				'back_to_vendors_url': reverse('admin:vendor_vendorprofile_changelist'),
			})
		return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)

	def _detail_redirect_url(self, profile, request):
		changelist_url = reverse('admin:vendor_vendorprofile_changelist')
		next_url = (request.POST.get('next_url') or '').strip()
		if next_url and next_url.startswith(changelist_url):
			return next_url
		if profile.verification_status == VendorProfile.VerificationStatus.PENDING:
			return f"{changelist_url}?verification_status__exact=PENDING"
		return changelist_url

	def approve_vendor_view(self, request, object_id):
		profile = self.get_object(request, object_id)
		if not profile:
			self.message_user(request, 'Vendor profile was not found.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:vendor_vendorprofile_changelist'))

		if request.method != 'POST':
			self.message_user(request, 'Approve action must be submitted from the detail page.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:vendor_vendorprofile_change', args=[profile.pk]))

		profile.verification_status = VendorProfile.VerificationStatus.APPROVED
		profile.save()
		try:
			self._send_verification_email(profile, is_approved=True)
		except Exception as exc:
			self.message_user(
				request,
				f'Vendor approved, but approval email could not be sent to {profile.user.email}: {exc}',
				level=messages.WARNING,
			)
		else:
			self.message_user(request, 'Vendor approved successfully and email sent.', level=messages.SUCCESS)

		return HttpResponseRedirect(self._detail_redirect_url(profile, request))

	def reject_vendor_view(self, request, object_id):
		profile = self.get_object(request, object_id)
		if not profile:
			self.message_user(request, 'Vendor profile was not found.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:vendor_vendorprofile_changelist'))

		if request.method != 'POST':
			self.message_user(request, 'Reject action must be submitted from the detail page.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:vendor_vendorprofile_change', args=[profile.pk]))

		reason = (request.POST.get('reason') or '').strip()
		if not reason:
			self.message_user(request, 'Rejection reason is required.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:vendor_vendorprofile_change', args=[profile.pk]))

		profile.verification_status = VendorProfile.VerificationStatus.REJECTED
		profile.rejection_reason = reason
		profile.save()
		try:
			self._send_verification_email(profile, is_approved=False)
		except Exception as exc:
			self.message_user(
				request,
				f'Vendor rejected, but rejection email could not be sent to {profile.user.email}: {exc}',
				level=messages.WARNING,
			)
		else:
			self.message_user(request, 'Vendor rejected successfully and email sent.', level=messages.WARNING)

		return HttpResponseRedirect(self._detail_redirect_url(profile, request))

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		url_name = getattr(getattr(request, 'resolver_match', None), 'url_name', '')
		# Detail pages and action URLs don't include verification_status__exact in query params,
		# so allow all statuses there to avoid false "doesn't exist" errors.
		if url_name.endswith(('_change', '_approve', '_reject')):
			return qs
		status_filter = (request.GET.get('verification_status__exact') or '').strip().upper()
		allowed_statuses = {
			VendorProfile.VerificationStatus.PENDING,
			VendorProfile.VerificationStatus.APPROVED,
			VendorProfile.VerificationStatus.REJECTED,
		}
		if status_filter in allowed_statuses:
			return qs.filter(verification_status=status_filter)
		return qs.filter(verification_status=VendorProfile.VerificationStatus.APPROVED)

	def get_list_display(self, request):
		status_filter = (request.GET.get('verification_status__exact') or '').strip().upper()
		if status_filter == VendorProfile.VerificationStatus.PENDING:
			return (
				'vendor_identity',
				'business_contact',
				'registered_on',
				'view_details',
			)
		return self.list_display

	def get_list_filter(self, request):
		status_filter = (request.GET.get('verification_status__exact') or '').strip().upper()
		if status_filter == VendorProfile.VerificationStatus.PENDING:
			return ()
		return self.list_filter

	def get_actions(self, request):
		actions = super().get_actions(request)
		status_filter = (request.GET.get('verification_status__exact') or '').strip().upper()
		if status_filter == VendorProfile.VerificationStatus.PENDING:
			return {}
		is_verification_page = status_filter in {
			VendorProfile.VerificationStatus.PENDING,
			VendorProfile.VerificationStatus.REJECTED,
		}

		if is_verification_page:
			actions.pop('deactivate_selected_vendors', None)
			actions.pop('reactivate_selected_vendors', None)
		else:
			actions.pop('approve_selected_vendors', None)
			actions.pop('reject_selected_vendors', None)

		return actions

	def changelist_view(self, request, extra_context=None):
		extra_context = extra_context or {}
		status_filter = (request.GET.get('verification_status__exact') or '').strip().upper()

		title_map = {
			VendorProfile.VerificationStatus.PENDING: 'Vendor Verifications',
			VendorProfile.VerificationStatus.REJECTED: 'Vendor Verification Queue (Rejected)',
			VendorProfile.VerificationStatus.APPROVED: 'Vendor Profiles (Approved)',
		}
		extra_context['title'] = title_map.get(status_filter, 'Vendor Profiles (Approved)')

		return super().changelist_view(request, extra_context=extra_context)

	def _format_dt(self, value):
		if not value:
			return '-'
		return value.strftime('%b %d, %Y %I:%M %p')

	def _verification_badge(self, status):
		label = dict(VendorProfile.VerificationStatus.choices).get(status, status or '-')
		styles = {
			VendorProfile.VerificationStatus.APPROVED: 'background:#e7f8ef;color:#065f46;border:1px solid #a7f3d0;',
			VendorProfile.VerificationStatus.REJECTED: 'background:#fdecec;color:#9f1239;border:1px solid #fecdd3;',
			VendorProfile.VerificationStatus.PENDING: 'background:#fff7e6;color:#92400e;border:1px solid #fcd9a1;',
		}
		style = styles.get(status, 'background:#f1f5f9;color:#334155;border:1px solid #cbd5e1;')
		return format_html('<span style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700;{}">{}</span>', style, label)

	def _account_badge(self, status):
		label = dict(VendorProfile.AccountStatus.choices).get(status, status or '-')
		styles = {
			VendorProfile.AccountStatus.ACTIVE: 'background:#e0f2fe;color:#0c4a6e;border:1px solid #bae6fd;',
			VendorProfile.AccountStatus.DEACTIVATED: 'background:#f3f4f6;color:#374151;border:1px solid #d1d5db;',
		}
		style = styles.get(status, 'background:#f1f5f9;color:#334155;border:1px solid #cbd5e1;')
		return format_html('<span style="display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700;{}">{}</span>', style, label)

	@admin.display(description='Vendor')
	def vendor_identity(self, obj):
		owner = obj.owner_full_name or '-'
		return format_html(
			'<div style="display:flex;flex-direction:column;line-height:1.25;">'
			'<strong style="font-size:13px;color:#0f172a;">{}</strong>'
			'<span style="font-size:11px;color:#64748b;">Owner: {}</span>'
			'</div>',
			obj.company_name,
			owner,
		)

	@admin.display(description='Contact')
	def business_contact(self, obj):
		username = getattr(obj.user, 'username', '-') or '-'
		email = getattr(obj.user, 'email', '-') or '-'
		phone = obj.contact_phone or '-'
		return format_html(
			'<div style="display:flex;flex-direction:column;line-height:1.25;gap:1px;">'
			'<span style="font-size:12px;color:#334155;">@{}</span>'
			'<span style="font-size:11px;color:#64748b;">{}</span>'
			'<span style="font-size:11px;color:#64748b;">{}</span>'
			'</div>',
			username,
			email,
			phone,
		)

	@admin.display(description='Account')
	def account_state(self, obj):
		return self._account_badge(obj.account_status)

	@admin.display(description='Registered')
	def registered_on(self, obj):
		return self._format_dt(obj.created_at)

	@admin.display(description='Identity')
	def identity_panel(self, obj):
		full_name = obj.owner_full_name or '-'
		username = getattr(obj.user, 'username', '-') or '-'
		email = getattr(obj.user, 'email', '-') or '-'
		phone = obj.contact_phone or '-'
		address = obj.address or '-'
		return format_html(
			'<div style="display:grid;gap:8px;font-size:12px;color:#334155;">'
			'<div><strong>Company:</strong> {}</div>'
			'<div><strong>Owner:</strong> {}</div>'
			'<div><strong>Username:</strong> @{}</div>'
			'<div><strong>Email:</strong> {}</div>'
			'<div><strong>Phone:</strong> {}</div>'
			'<div><strong>Address:</strong> {}</div>'
			'</div>',
			obj.company_name,
			full_name,
			username,
			email,
			phone,
			address,
		)

	@admin.display(description='Payment and Tax')
	def payment_panel(self, obj):
		account_holder_name = (obj.account_holder_name or '').strip()
		if not account_holder_name:
			account_holder_name = (obj.owner_full_name or '').strip() or 'Not submitted'

		esewa_number = (obj.mobile_payment_number or '').strip()
		if not esewa_number:
			esewa_number = (obj.contact_phone or '').strip() or 'Not submitted'

		pan_number = obj.pan_vat_number or '-'
		return format_html(
			'<div style="display:grid;gap:8px;font-size:12px;color:#334155;">'
			'<div><strong>Account Holder:</strong> {}</div>'
			'<div><strong>eSewa Number:</strong> {}</div>'
			'<div><strong>PAN/VAT Number:</strong> {}</div>'
			'</div>',
			account_holder_name,
			esewa_number,
			pan_number,
		)

	@admin.display(description='Verification Summary')
	def verification_panel(self, obj):
		return format_html(
			'<div style="display:grid;gap:8px;font-size:12px;color:#334155;">'
			'<div><strong>Verification Status:</strong> {}</div>'
			'</div>',
			self._verification_badge(obj.verification_status),
		)

	@admin.display(description='Timeline')
	def timeline_panel(self, obj):
		return format_html(
			'<div style="display:grid;gap:8px;font-size:12px;color:#334155;">'
			'<div><strong>Submitted At:</strong> {}</div>'
			'<div><strong>Verified At:</strong> {}</div>'
			'<div><strong>Created At:</strong> {}</div>'
			'<div><strong>Updated At:</strong> {}</div>'
			'</div>',
			self._format_dt(obj.submitted_at),
			self._format_dt(obj.verified_at),
			self._format_dt(obj.created_at),
			self._format_dt(obj.updated_at),
		)

	@admin.display(description='Business Context')
	def business_context_panel(self, obj):
		return format_html(
			'<div style="display:grid;gap:8px;font-size:12px;color:#334155;">'
			'<div><strong>Business Registration Number:</strong> {}</div>'
			'<div><strong>Owner National ID:</strong> {}</div>'
			'<div><strong>Account Status:</strong> {}</div>'
			'</div>',
			obj.business_registration_number or '-',
			obj.owner_national_id or '-',
			self._account_badge(obj.account_status),
		)

	@admin.display(description='Details')
	def view_details(self, obj):
		url = reverse('admin:vendor_vendorprofile_change', args=[obj.pk])
		return format_html('<a class="button" href="{}">View details</a>', url)

	@admin.display(description='Certificate Preview')
	def business_certificate_preview(self, obj):
		file_field = getattr(obj, 'business_registration_certificate', None)
		if not file_field:
			return '-'

		file_name = str(getattr(file_field, 'name', '') or '').lower()
		file_url = getattr(file_field, 'url', '')
		if not file_url:
			return '-'

		if file_name.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
			return format_html(
				'<a href="{0}" target="_blank"><img src="{0}" style="max-height:120px; max-width:180px; border-radius:6px; border:1px solid #ddd;" /></a>',
				file_url,
			)
		return format_html('<a href="{}" target="_blank">Open uploaded certificate</a>', file_url)

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

	@admin.action(description='Deactivate selected vendors (requires reason)')
	def deactivate_selected_vendors(self, request, queryset):
		if 'apply' in request.POST:
			form = DeactivateVendorsForm(request.POST)
			if form.is_valid():
				reason = form.cleaned_data['reason']
				selected_ids = request.POST.getlist('_selected_action')
				target_qs = VendorProfile.objects.filter(pk__in=selected_ids)

				updated = 0
				for profile in target_qs:
					profile.account_status = VendorProfile.AccountStatus.DEACTIVATED
					profile.status_reason = reason
					profile.save()
					updated += 1

				self.message_user(
					request,
					f'{updated} vendor(s) deactivated. Packages, activities, and hot sales have been disabled automatically.',
					level=messages.WARNING,
				)
				return None
		else:
			form = DeactivateVendorsForm(
				initial={'_selected_action': request.POST.getlist(ACTION_CHECKBOX_NAME)}
			)

		context = {
			**self.admin_site.each_context(request),
			'opts': self.model._meta,
			'vendors': queryset,
			'form': form,
			'title': 'Deactivate selected vendors',
		}
		return TemplateResponse(request, 'admin/vendor/deactivate_selected_vendors.html', context)

	@admin.action(description='Reactivate selected vendors')
	def reactivate_selected_vendors(self, request, queryset):
		updated = 0
		for profile in queryset:
			profile.account_status = VendorProfile.AccountStatus.ACTIVE
			profile.status_reason = ''
			profile.save()
			updated += 1

		self.message_user(
			request,
			f'{updated} vendor(s) reactivated. Their approved packages and activities have been automatically re-enabled.',
			level=messages.SUCCESS,
		)

	@admin.display(description='eSewa Number')
	def masked_mobile_payment_number(self, obj):
		return obj.masked_mobile_payment_number
