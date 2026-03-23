from django.contrib import admin
from .models import VendorProfile


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
	list_display = (
		'company_name',
		'owner_full_name',
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
		'user__username',
		'user__email',
		'contact_phone',
	)
	readonly_fields = ('submitted_at', 'verified_at', 'created_at', 'updated_at')
	fieldsets = (
		('Vendor Identity', {
			'fields': ('user', 'company_name', 'owner_full_name', 'owner_national_id', 'contact_phone', 'address'),
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
