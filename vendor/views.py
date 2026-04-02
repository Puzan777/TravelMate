from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from app.models import Activity, ActivityImage, Booking, HotSale, Inquiry, Package, PackageImage
from .forms import (
	PackageItineraryFormSet,
	VendorActivityForm,
	VendorHotSaleForm,
	VendorInquiryReplyForm,
	VendorPackageForm,
	VendorRegistrationForm,
)
from .image_utils import (
	DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES,
	DEFAULT_ALLOWED_IMAGE_EXTENSIONS,
	DEFAULT_MAX_IMAGES,
	DEFAULT_MAX_IMAGE_SIZE,
	parse_selected_primary_index,
	set_primary_image,
	validate_uploaded_images,
)
from .models import VendorProfile


MAX_ACTIVITY_IMAGES = DEFAULT_MAX_IMAGES
MAX_ACTIVITY_IMAGE_SIZE = DEFAULT_MAX_IMAGE_SIZE
ALLOWED_ACTIVITY_IMAGE_EXTENSIONS = DEFAULT_ALLOWED_IMAGE_EXTENSIONS
ALLOWED_ACTIVITY_IMAGE_CONTENT_TYPES = DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES

MAX_PACKAGE_IMAGES = DEFAULT_MAX_IMAGES
MAX_PACKAGE_IMAGE_SIZE = DEFAULT_MAX_IMAGE_SIZE
ALLOWED_PACKAGE_IMAGE_EXTENSIONS = DEFAULT_ALLOWED_IMAGE_EXTENSIONS
ALLOWED_PACKAGE_IMAGE_CONTENT_TYPES = DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES


def _ensure_package_images_seed(package):
	if package.images.exists() or not package.image:
		return
	PackageImage.objects.create(package=package, image=package.image.name, is_primary=True)


def _sync_package_cover_image(package):
	primary_image = package.images.filter(is_primary=True).first() or package.images.first()
	if primary_image is None:
		return
	if package.image != primary_image.image.name:
		package.image = primary_image.image.name
		package.save(update_fields=['image'])


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
		'hot_sale_count': HotSale.objects.filter(
			Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile),
			is_active=True,
		).count(),
		'booking_count': Booking.objects.filter(package__vendor=vendor_profile).count(),
		'inquiry_count': Inquiry.objects.filter(package__vendor=vendor_profile).count(),
		'recent_bookings': recent_bookings,
		'recent_inquiries': recent_inquiries,
		'recent_hot_sales': HotSale.objects.filter(
			Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile)
		)
			.select_related('package', 'package__destination', 'activity')
			.prefetch_related('activity__images')
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
def activity_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	activities = Activity.objects.filter(vendor=vendor_profile).select_related('category').order_by('name')
	return render(
		request,
		'vendor/activity_list.html',
		{
			'activities': activities,
			'vendor_profile': vendor_profile,
		},
	)


@login_required
def activity_create(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	if request.method == 'POST':
		form = VendorActivityForm(request.POST)
		image_files = request.FILES.getlist('images')
		selected_new_primary_index = parse_selected_primary_index(
			request.POST.get('selected_new_primary_index'),
			len(image_files),
		)
		image_error = validate_uploaded_images(
			image_files,
			existing_count=0,
			entity_label='activity',
			max_images=MAX_ACTIVITY_IMAGES,
			max_size_bytes=MAX_ACTIVITY_IMAGE_SIZE,
			allowed_extensions=ALLOWED_ACTIVITY_IMAGE_EXTENSIONS,
			allowed_content_types=ALLOWED_ACTIVITY_IMAGE_CONTENT_TYPES,
		)
		if image_error:
			form.add_error(None, image_error)
		if not image_files:
			form.add_error(None, 'Please upload at least one activity image.')
		if form.is_valid():
			with transaction.atomic():
				activity = form.save(commit=False)
				activity.vendor = vendor_profile
				activity.save()
				primary_index = selected_new_primary_index if selected_new_primary_index is not None else 0
				for index, image_file in enumerate(image_files):
					ActivityImage.objects.create(activity=activity, image=image_file, is_primary=(index == primary_index))
			messages.success(request, 'Activity created successfully.')
			return redirect('vendor:activity_list')
	else:
		form = VendorActivityForm()

	return render(
		request,
		'vendor/activity_form.html',
		{
			'form': form,
			'page_title': 'Create Activity',
			'submit_label': 'Create Activity',
			'activity_images': [],
		},
	)


@login_required
def activity_edit(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	activity = get_object_or_404(Activity, pk=pk, vendor=vendor_profile)
	if request.method == 'POST':
		form = VendorActivityForm(request.POST, instance=activity)
		remove_image_ids = request.POST.getlist('remove_image_ids')
		images_to_remove = activity.images.filter(pk__in=remove_image_ids)
		remaining_count = activity.images.exclude(pk__in=images_to_remove.values_list('pk', flat=True)).count()
		image_files = request.FILES.getlist('images')
		selected_new_primary_index = parse_selected_primary_index(
			request.POST.get('selected_new_primary_index'),
			len(image_files),
		)
		image_error = validate_uploaded_images(
			image_files,
			existing_count=remaining_count,
			entity_label='activity',
			max_images=MAX_ACTIVITY_IMAGES,
			max_size_bytes=MAX_ACTIVITY_IMAGE_SIZE,
			allowed_extensions=ALLOWED_ACTIVITY_IMAGE_EXTENSIONS,
			allowed_content_types=ALLOWED_ACTIVITY_IMAGE_CONTENT_TYPES,
		)
		if image_error:
			form.add_error(None, image_error)
		if remaining_count + len(image_files) == 0:
			form.add_error(None, 'Please keep at least one activity image.')

		if form.is_valid():
			with transaction.atomic():
				form.save()
				images_to_remove.delete()

				has_existing_images = activity.images.exists()
				new_images = []
				for index, image_file in enumerate(image_files):
					new_images.append(ActivityImage.objects.create(
						activity=activity,
						image=image_file,
						is_primary=(not has_existing_images and index == 0),
					))

				preferred_primary_id = request.POST.get('primary_image_id')
				if preferred_primary_id and preferred_primary_id.isdigit():
					set_primary_image(activity.images, preferred_image_id=int(preferred_primary_id))
				elif selected_new_primary_index is not None and selected_new_primary_index < len(new_images):
					set_primary_image(activity.images, preferred_image_id=new_images[selected_new_primary_index].pk)
				else:
					set_primary_image(activity.images)

			messages.success(request, 'Activity updated successfully.')
			return redirect('vendor:activity_list')
	else:
		form = VendorActivityForm(instance=activity)

	return render(
		request,
		'vendor/activity_form.html',
		{
			'form': form,
			'page_title': 'Edit Activity',
			'submit_label': 'Save Changes',
			'activity': activity,
			'activity_images': activity.images.all().order_by('-is_primary', 'created_at'),
		},
	)


@login_required
def activity_delete(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	activity = get_object_or_404(Activity, pk=pk, vendor=vendor_profile)
	if request.method == 'POST':
		activity.delete()
		messages.success(request, 'Activity deleted successfully.')
		return redirect('vendor:activity_list')

	return render(
		request,
		'vendor/activity_confirm_delete.html',
		{
			'activity': activity,
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
		image_files = request.FILES.getlist('images')
		selected_new_primary_index = parse_selected_primary_index(
			request.POST.get('selected_new_primary_index'),
			len(image_files),
		)
		image_error = validate_uploaded_images(
			image_files,
			existing_count=0,
			entity_label='package',
			max_images=MAX_PACKAGE_IMAGES,
			max_size_bytes=MAX_PACKAGE_IMAGE_SIZE,
			allowed_extensions=ALLOWED_PACKAGE_IMAGE_EXTENSIONS,
			allowed_content_types=ALLOWED_PACKAGE_IMAGE_CONTENT_TYPES,
		)
		if image_error:
			form.add_error(None, image_error)
		if not image_files:
			form.add_error(None, 'Please upload at least one package image.')
		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				primary_index = selected_new_primary_index if selected_new_primary_index is not None else 0
				package = form.save(commit=False)
				package.vendor = vendor_profile
				package.image = image_files[primary_index]
				package.save()
				for index, image_file in enumerate(image_files):
					PackageImage.objects.create(package=package, image=image_file, is_primary=(index == primary_index))
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
			'package_images': [],
			'package_cover_image': None,
		},
	)


@login_required
def package_edit(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	package = get_object_or_404(Package, pk=pk, vendor=vendor_profile)
	_ensure_package_images_seed(package)
	if request.method == 'POST':
		form = VendorPackageForm(request.POST, request.FILES, instance=package, vendor_profile=vendor_profile)
		formset = PackageItineraryFormSet(request.POST, instance=package, prefix='itinerary')
		remove_image_ids = request.POST.getlist('remove_image_ids')
		images_to_remove = package.images.filter(pk__in=remove_image_ids)
		remaining_count = package.images.exclude(pk__in=images_to_remove.values_list('pk', flat=True)).count()
		image_files = request.FILES.getlist('images')
		selected_new_primary_index = parse_selected_primary_index(
			request.POST.get('selected_new_primary_index'),
			len(image_files),
		)
		image_error = validate_uploaded_images(
			image_files,
			existing_count=remaining_count,
			entity_label='package',
			max_images=MAX_PACKAGE_IMAGES,
			max_size_bytes=MAX_PACKAGE_IMAGE_SIZE,
			allowed_extensions=ALLOWED_PACKAGE_IMAGE_EXTENSIONS,
			allowed_content_types=ALLOWED_PACKAGE_IMAGE_CONTENT_TYPES,
		)
		if image_error:
			form.add_error(None, image_error)
		if remaining_count + len(image_files) == 0:
			form.add_error(None, 'Please keep at least one package image.')
		if form.is_valid() and formset.is_valid():
			with transaction.atomic():
				form.save()
				formset.save()
				images_to_remove.delete()

				has_existing_images = package.images.exists()
				new_images = []
				for index, image_file in enumerate(image_files):
					new_images.append(PackageImage.objects.create(
						package=package,
						image=image_file,
						is_primary=(not has_existing_images and index == 0),
					))

				preferred_primary_id = request.POST.get('primary_image_id')
				if preferred_primary_id and preferred_primary_id.isdigit():
					set_primary_image(package.images, preferred_image_id=int(preferred_primary_id))
				elif selected_new_primary_index is not None and selected_new_primary_index < len(new_images):
					set_primary_image(package.images, preferred_image_id=new_images[selected_new_primary_index].pk)
				else:
					set_primary_image(package.images)
				_sync_package_cover_image(package)

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
			'package': package,
			'package_images': package.images.all().order_by('-is_primary', 'created_at'),
			'package_cover_image': package.images.filter(is_primary=True).first() or package.images.first(),
		},
	)


@login_required
def hot_sale_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	hot_sales = HotSale.objects.filter(
		Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile)
	).select_related('package', 'activity').prefetch_related('activity__images').order_by('-created_at')
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
			with transaction.atomic():
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

	hot_sale = get_object_or_404(
		HotSale.objects.filter(Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile)),
		pk=pk,
	)
	if request.method == 'POST':
		form = VendorHotSaleForm(request.POST, instance=hot_sale, vendor_profile=vendor_profile)
		if form.is_valid():
			with transaction.atomic():
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
