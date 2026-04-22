from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class VendorProfile(models.Model):
	class VerificationStatus(models.TextChoices):
		PENDING = 'PENDING', 'Pending'
		APPROVED = 'APPROVED', 'Approved'
		REJECTED = 'REJECTED', 'Rejected'

	class AccountStatus(models.TextChoices):
		ACTIVE = 'ACTIVE', 'Active'
		DEACTIVATED = 'DEACTIVATED', 'Deactivated'

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
	account_holder_name = models.CharField(max_length=150, blank=True)
	mobile_payment_number = models.CharField(max_length=20, blank=True, null=True)
	submitted_at = models.DateTimeField(null=True, blank=True)
	verified_at = models.DateTimeField(null=True, blank=True)
	verification_status = models.CharField(
		max_length=20,
		choices=VerificationStatus.choices,
		default=VerificationStatus.PENDING,
	)
	account_status = models.CharField(
		max_length=20,
		choices=AccountStatus.choices,
		default=AccountStatus.ACTIVE,
	)
	status_reason = models.TextField(blank=True)
	status_changed_at = models.DateTimeField(null=True, blank=True)
	rejection_reason = models.TextField(blank=True)
	is_approved = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['company_name']

	def __str__(self):
		return self.company_name

	@property
	def masked_mobile_payment_number(self):
		number = (self.mobile_payment_number or '').strip()
		if not number:
			return '-'
		if len(number) <= 4:
			return '*' * len(number)
		return f"{'*' * (len(number) - 4)}{number[-4:]}"

	def save(self, *args, **kwargs):
		previous_status = None
		if self.pk:
			previous_status = (
				VendorProfile.objects
				.filter(pk=self.pk)
				.values_list('account_status', flat=True)
				.first()
			)

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

		if previous_status != self.account_status:
			self.status_changed_at = timezone.now()

		if self.account_status == self.AccountStatus.ACTIVE:
			self.status_reason = ''

		super().save(*args, **kwargs)

		if (
			self.account_status == self.AccountStatus.DEACTIVATED
			and previous_status != self.AccountStatus.DEACTIVATED
		):
			from app.models import Activity, HotSale, Package

			Package.objects.filter(vendor=self, is_active=True).update(is_active=False)
			Activity.objects.filter(vendor=self, is_active=True).update(is_active=False)
			HotSale.objects.filter(
				Q(package__vendor=self) | Q(activity__vendor=self),
				is_active=True,
			).update(is_active=False)
			
		elif (
			self.account_status == self.AccountStatus.ACTIVE
			and previous_status == self.AccountStatus.DEACTIVATED
		):
			from app.models import Activity, Package, ApprovalStatus
			
			Package.objects.filter(
				vendor=self, approval_status=ApprovalStatus.APPROVED
			).update(is_active=True)
			
			Activity.objects.filter(
				vendor=self, approval_status=ApprovalStatus.APPROVED
			).update(is_active=True)
