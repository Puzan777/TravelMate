from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from app.models import Booking, Inquiry, Package
from .forms import VendorRegistrationForm
from .models import VendorProfile


def register(request):
	if request.user.is_authenticated:
		messages.info(request, 'You are already logged in. Please use another account for vendor registration.')
		return redirect('home')

	if request.method == 'POST':
		form = VendorRegistrationForm(request.POST, request.FILES)
		if form.is_valid():
			form.save()
			messages.success(
				request,
				'Vendor registration submitted successfully. Please wait for admin verification.',
			)
			return redirect('login')
	else:
		form = VendorRegistrationForm()

	return render(request, 'vendor/register.html', {'form': form})


@login_required
def dashboard(request):
	if not (request.user.is_superuser or request.user.is_staff or request.user.role == 'VENDOR'):
		messages.error(request, 'Vendor access is required to open the vendor dashboard.')
		return redirect('home')

	profile, _ = VendorProfile.objects.get_or_create(
		user=request.user,
		defaults={
			'company_name': request.user.get_full_name() or request.user.username,
		},
	)

	if request.user.role == 'VENDOR' and profile.verification_status != VendorProfile.VerificationStatus.APPROVED:
		if profile.verification_status == VendorProfile.VerificationStatus.REJECTED and profile.rejection_reason:
			messages.error(request, f'Your vendor account was rejected: {profile.rejection_reason}')
		else:
			messages.warning(request, 'Your vendor registration is pending approval. Dashboard access is blocked until approval.')
		return redirect('home')

	package_qs = Package.objects.filter(vendor=profile)
	recent_bookings = Booking.objects.filter(package__vendor=profile).select_related('package', 'user')[:5]
	recent_inquiries = Inquiry.objects.filter(package__vendor=profile).select_related('package', 'user')[:5]

	context = {
		'vendor_profile': profile,
		'package_count': package_qs.count(),
		'active_package_count': package_qs.filter(is_active=True).count(),
		'booking_count': Booking.objects.filter(package__vendor=profile).count(),
		'inquiry_count': Inquiry.objects.filter(package__vendor=profile).count(),
		'recent_bookings': recent_bookings,
		'recent_inquiries': recent_inquiries,
	}
	return render(request, 'vendor/dashboard.html', context)
