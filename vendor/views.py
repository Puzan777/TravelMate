from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from app.models import Booking, HotSale, Inquiry, Package
from .forms import (
	PackageItineraryFormSet,
	VendorHotSaleForm,
	VendorInquiryReplyForm,
	VendorPackageForm,
	VendorRegistrationForm,
)
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
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	package_qs = Package.objects.filter(vendor=vendor_profile)
	recent_bookings = Booking.objects.filter(package__vendor=vendor_profile).select_related('package', 'user')[:5]
	recent_inquiries = Inquiry.objects.filter(package__vendor=vendor_profile).select_related('package', 'user')[:5]

	context = {
		'vendor_profile': vendor_profile,
		'package_count': package_qs.count(),
		'active_package_count': package_qs.filter(is_active=True).count(),
		'hot_sale_count': HotSale.objects.filter(package__vendor=vendor_profile, is_active=True).count(),
		'booking_count': Booking.objects.filter(package__vendor=vendor_profile).count(),
		'inquiry_count': Inquiry.objects.filter(package__vendor=vendor_profile).count(),
		'recent_bookings': recent_bookings,
		'recent_inquiries': recent_inquiries,
		'recent_hot_sales': HotSale.objects.filter(package__vendor=vendor_profile)
			.select_related('package', 'package__destination')
			.order_by('-updated_at')[:8],
	}
	return render(request, 'vendor/dashboard.html', context)


def _get_approved_vendor_profile(request):
	if not (request.user.is_superuser or request.user.is_staff or request.user.role == 'VENDOR'):
		messages.error(request, 'Vendor access is required to open the vendor dashboard.')
		return None

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
		return None

	return profile


@login_required
def package_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	packages = Package.objects.filter(vendor=vendor_profile).select_related('destination').order_by('-created_at')
	return render(
		request,
		'vendor/package_list.html',
		{
			'packages': packages,
			'vendor_profile': vendor_profile,
		},
	)


@login_required
def package_create(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	if request.method == 'POST':
		form = VendorPackageForm(request.POST, request.FILES, vendor_profile=vendor_profile)
		formset = PackageItineraryFormSet(request.POST, prefix='itinerary')
		if form.is_valid() and formset.is_valid():
			package = form.save(commit=False)
			package.vendor = vendor_profile
			package.save()
			formset.instance = package
			formset.save()
			messages.success(request, 'Package created successfully.')
			return redirect('vendor:package_list')
	else:
		form = VendorPackageForm(vendor_profile=vendor_profile)
		formset = PackageItineraryFormSet(prefix='itinerary')

	return render(
		request,
		'vendor/package_form.html',
		{
			'form': form,
			'itinerary_formset': formset,
			'page_title': 'Create Package',
			'submit_label': 'Create Package',
		},
	)


@login_required
def package_edit(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	package = get_object_or_404(Package, pk=pk, vendor=vendor_profile)
	if request.method == 'POST':
		form = VendorPackageForm(request.POST, request.FILES, instance=package, vendor_profile=vendor_profile)
		formset = PackageItineraryFormSet(request.POST, instance=package, prefix='itinerary')
		if form.is_valid() and formset.is_valid():
			form.save()
			formset.save()
			messages.success(request, 'Package updated successfully.')
			return redirect('vendor:package_list')
	else:
		form = VendorPackageForm(instance=package, vendor_profile=vendor_profile)
		formset = PackageItineraryFormSet(instance=package, prefix='itinerary')

	return render(
		request,
		'vendor/package_form.html',
		{
			'form': form,
			'itinerary_formset': formset,
			'page_title': 'Edit Package',
			'submit_label': 'Save Changes',
		},
	)


@login_required
def hot_sale_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	hot_sales = HotSale.objects.filter(package__vendor=vendor_profile).select_related('package').order_by('-created_at')
	return render(
		request,
		'vendor/hot_sale_list.html',
		{
			'hot_sales': hot_sales,
			'vendor_profile': vendor_profile,
		},
	)


@login_required
def hot_sale_create(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	if request.method == 'POST':
		form = VendorHotSaleForm(request.POST, vendor_profile=vendor_profile)
		if form.is_valid():
			form.save()
			messages.success(request, 'Hot sale created successfully.')
			return redirect('vendor:hot_sale_list')
	else:
		form = VendorHotSaleForm(vendor_profile=vendor_profile)

	return render(
		request,
		'vendor/hot_sale_form.html',
		{
			'form': form,
			'page_title': 'Create Hot Sale',
			'submit_label': 'Create Hot Sale',
		},
	)


@login_required
def hot_sale_edit(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	hot_sale = get_object_or_404(HotSale, pk=pk, package__vendor=vendor_profile)
	if request.method == 'POST':
		form = VendorHotSaleForm(request.POST, instance=hot_sale, vendor_profile=vendor_profile)
		if form.is_valid():
			form.save()
			messages.success(request, 'Hot sale updated successfully.')
			return redirect('vendor:hot_sale_list')
	else:
		form = VendorHotSaleForm(instance=hot_sale, vendor_profile=vendor_profile)

	return render(
		request,
		'vendor/hot_sale_form.html',
		{
			'form': form,
			'page_title': 'Edit Hot Sale',
			'submit_label': 'Save Changes',
		},
	)


@login_required
def inquiry_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	inquiries = Inquiry.objects.filter(package__vendor=vendor_profile).select_related('package', 'user').order_by('-created_at')
	return render(
		request,
		'vendor/inquiry_list.html',
		{
			'inquiries': inquiries,
			'vendor_profile': vendor_profile,
		},
	)


@login_required
def booking_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	bookings = Booking.objects.filter(package__vendor=vendor_profile).select_related('package', 'user').order_by('-created_at')
	return render(
		request,
		'vendor/booking_list.html',
		{
			'bookings': bookings,
			'vendor_profile': vendor_profile,
		},
	)


@login_required
def inquiry_reply(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	inquiry = get_object_or_404(Inquiry, pk=pk, package__vendor=vendor_profile)
	if request.method == 'POST':
		form = VendorInquiryReplyForm(request.POST, instance=inquiry)
		if form.is_valid():
			form.save()
			messages.success(request, 'Inquiry reply saved successfully.')
			return redirect('vendor:inquiry_list')
	else:
		form = VendorInquiryReplyForm(instance=inquiry)

	return render(
		request,
		'vendor/inquiry_reply.html',
		{
			'form': form,
			'inquiry': inquiry,
		},
	)
