from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from app.models import (
	Activity,
	ActivityCategory,
	ApprovalStatus,
	CustomUser,
	Destination,
	Inquiry,
	Package,
)
from vendor.models import VendorProfile


class InquiryFlowTests(TestCase):
	def setUp(self):
		self.customer = CustomUser.objects.create_user(
			username='customer1',
			email='customer1@example.com',
			password='testpass123',
			role=CustomUser.Role.CUSTOMER,
		)
		self.vendor_user = CustomUser.objects.create_user(
			username='vendor1',
			email='vendor1@example.com',
			password='testpass123',
			role=CustomUser.Role.VENDOR,
		)
		self.vendor_profile = VendorProfile.objects.create(
			user=self.vendor_user,
			company_name='Vendor Co',
			verification_status=VendorProfile.VerificationStatus.APPROVED,
		)
		self.destination = Destination.objects.create(name='Nepal')
		self.category = ActivityCategory.objects.create(name='Adventure')

		self.package = Package.objects.create(
			title='Everest Starter Trek',
			vendor=self.vendor_profile,
			category=Package.Category.TREKKING,
			image=SimpleUploadedFile('package.jpg', b'filecontent', content_type='image/jpeg'),
			price='1999.00',
			description='A classic mountain trek package.',
			duration='7 days',
			destination=self.destination,
			approval_status=ApprovalStatus.APPROVED,
			is_active=True,
		)
		self.activity = Activity.objects.create(
			vendor=self.vendor_profile,
			category=self.category,
			name='River Rafting',
			description='High-energy river rafting activity.',
			destination=self.destination,
			price='149.00',
			duration='1 day',
			difficulty_level=Activity.DifficultyLevel.MODERATE,
			approval_status=ApprovalStatus.APPROVED,
			is_active=True,
		)

	def test_package_inquiry_submit_and_visibility(self):
		self.client.login(username='customer1', password='testpass123')
		response = self.client.post(
			reverse('package_detail', kwargs={'slug': self.package.slug}),
			{
				'form_type': 'inquiry',
				'message': 'I need details about accommodation.',
			},
		)

		self.assertEqual(response.status_code, 302)
		inquiry = Inquiry.objects.get(package=self.package, user=self.customer)
		self.assertIsNone(inquiry.activity)
		self.assertEqual(inquiry.message, 'I need details about accommodation.')

		profile_response = self.client.get(reverse('profile'))
		self.assertContains(profile_response, self.package.title)

		self.client.logout()
		self.client.login(username='vendor1', password='testpass123')
		vendor_response = self.client.get(reverse('vendor:inquiry_list'))
		self.assertContains(vendor_response, self.package.title)

	def test_activity_inquiry_submit_and_visibility(self):
		self.client.login(username='customer1', password='testpass123')
		response = self.client.post(
			reverse('activity_detail', kwargs={'pk': self.activity.pk}),
			{
				'form_type': 'inquiry',
				'message': 'Can beginners join this activity?',
			},
		)

		self.assertEqual(response.status_code, 302)
		inquiry = Inquiry.objects.get(activity=self.activity, user=self.customer)
		self.assertIsNone(inquiry.package)
		self.assertEqual(inquiry.message, 'Can beginners join this activity?')

		profile_response = self.client.get(reverse('profile'))
		self.assertContains(profile_response, self.activity.name)

		self.client.logout()
		self.client.login(username='vendor1', password='testpass123')
		vendor_response = self.client.get(reverse('vendor:inquiry_list'))
		self.assertContains(vendor_response, self.activity.name)
