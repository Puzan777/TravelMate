from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from app.models import Booking, Inquiry, Package
from .models import VendorProfile


@login_required
def dashboard(request):
	profile, _ = VendorProfile.objects.get_or_create(
		user=request.user,
		defaults={
			'company_name': request.user.get_full_name() or request.user.username,
		},
	)

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
