from django.contrib import admin
from .models import VendorProfile


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
	list_display = ('company_name', 'owner_full_name', 'pan_vat_number', 'user', 'is_approved', 'created_at')
	list_filter = ('is_approved', 'created_at')
	search_fields = (
		'company_name',
		'owner_full_name',
		'pan_vat_number',
		'business_registration_number',
		'user__username',
		'user__email',
		'contact_phone',
	)
