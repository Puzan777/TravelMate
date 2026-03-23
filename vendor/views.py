from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import VendorProfile


@login_required
def dashboard(request):
	profile, _ = VendorProfile.objects.get_or_create(
		user=request.user,
		defaults={
			'company_name': request.user.get_full_name() or request.user.username,
		},
	)
	return render(request, 'vendor/dashboard.html', {'vendor_profile': profile})
