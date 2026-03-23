from django.conf import settings
from django.db import models
from django.utils import timezone


class VendorProfile(models.Model):
	class VerificationStatus(models.TextChoices):
		PENDING = 'PENDING', 'Pending'
		APPROVED = 'APPROVED', 'Approved'
		REJECTED = 'REJECTED', 'Rejected'

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='vendor_profile',
	)
	company_name = models.CharField(max_length=150)
	owner_full_name = models.CharField(max_length=150, blank=True)
	pan_vat_number = models.CharField(max_length=50, blank=True)
	business_registration_number = models.CharField(max_length=100, blank=True)
	business_registration_certificate = models.FileField(upload_to='vendor_documents/', blank=True, null=True)
	owner_national_id = models.CharField(max_length=100, blank=True)
	contact_phone = models.CharField(max_length=30, blank=True)
	address = models.CharField(max_length=255, blank=True)
	submitted_at = models.DateTimeField(null=True, blank=True)
	verified_at = models.DateTimeField(null=True, blank=True)
	verification_status = models.CharField(
		max_length=20,
		choices=VerificationStatus.choices,
		default=VerificationStatus.PENDING,
	)
	rejection_reason = models.TextField(blank=True)
	is_approved = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['company_name']

	def __str__(self):
		return self.company_name

	def save(self, *args, **kwargs):
		if self.submitted_at is None:
			self.submitted_at = timezone.now()

		if self.verification_status == self.VerificationStatus.APPROVED:
			self.is_approved = True
			if self.verified_at is None:
				self.verified_at = timezone.now()
			self.rejection_reason = ''
		elif self.verification_status == self.VerificationStatus.REJECTED:
			self.is_approved = False
			if self.verified_at is None:
				self.verified_at = timezone.now()
		else:
			self.is_approved = False
			self.verified_at = None
			self.rejection_reason = ''

		super().save(*args, **kwargs)
