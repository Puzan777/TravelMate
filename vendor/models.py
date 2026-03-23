from django.conf import settings
from django.db import models


class VendorProfile(models.Model):
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='vendor_profile',
	)
	company_name = models.CharField(max_length=150)
	contact_phone = models.CharField(max_length=30, blank=True)
	address = models.CharField(max_length=255, blank=True)
	is_approved = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['company_name']

	def __str__(self):
		return self.company_name
