import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from app.models import (
	Activity,
	ActivityCategory,
	ActivityImage,
	ActivityUnavailableDate,
	ApprovalStatus,
	Booking,
	HotSale,
	Inquiry,
	Package,
	PackageImage,
	PackageUnavailableDate,
)
from .forms import (
	PackageItineraryFormSet,
	VendorActivityUnavailableDateForm,
	VendorActivityForm,
	VendorHotSaleForm,
	VendorInquiryReplyForm,
	VendorPackageUnavailableDateForm,
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
	visible_bookings = Booking.objects.visible_in_listings()
	recent_bookings = (
		visible_bookings
		.filter(package__vendor=vendor_profile)
		.select_related('package', 'user')[:5]
	)
	recent_inquiries = Inquiry.objects.filter(package__vendor=vendor_profile).select_related('package', 'user')[:5]

	context = {
		'vendor_profile': vendor_profile,
		'package_count': package_qs.count(),
		'active_package_count': package_qs.filter(is_active=True).count(),
		'hot_sale_count': HotSale.objects.filter(
			Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile),
			is_active=True,
		).count(),
		'booking_count': visible_bookings.filter(package__vendor=vendor_profile).count(),
		'inquiry_count': Inquiry.objects.filter(package__vendor=vendor_profile).count(),
		'recent_bookings': recent_bookings,
		'recent_inquiries': recent_inquiries,
		'recent_hot_sales': HotSale.objects.filter(
			Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile)
		)
			.select_related('package', 'package__destination', 'activity')
			.prefetch_related('activity__images')
			.order_by('-updated_at')[:8],
		'rejected_package_count': Package.objects.filter(vendor=vendor_profile, approval_status=ApprovalStatus.REJECTED).count(),
		'rejected_activity_count': Activity.objects.filter(vendor=vendor_profile, approval_status=ApprovalStatus.REJECTED).count(),
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

	if request.user.role == 'VENDOR' and profile.account_status == VendorProfile.AccountStatus.DEACTIVATED:
		messages.error(request, 'Your vendor account has been deactivated. Please contact support for assistance.')
		return None

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

	search_query = request.GET.get('q', '').strip()
	selected_status = request.GET.get('status', 'all').upper()
	selected_active = request.GET.get('active', 'all').lower()
	selected_category = request.GET.get('category', 'all').upper()

	valid_statuses = {choice[0] for choice in ApprovalStatus.choices}
	valid_categories = {choice[0] for choice in Package.Category.choices}

	packages = Package.objects.filter(vendor=vendor_profile).select_related('destination')

	if search_query:
		packages = packages.filter(
			Q(title__icontains=search_query)
			| Q(description__icontains=search_query)
			| Q(destination__name__icontains=search_query)
			| Q(region__icontains=search_query)
			| Q(city__icontains=search_query)
		)

	if selected_status in valid_statuses:
		packages = packages.filter(approval_status=selected_status)
	else:
		selected_status = 'all'

	if selected_active == 'active':
		packages = packages.filter(is_active=True)
	elif selected_active == 'inactive':
		packages = packages.filter(is_active=False)
	else:
		selected_active = 'all'

	if selected_category in valid_categories:
		packages = packages.filter(category=selected_category)
	else:
		selected_category = 'all'

	packages = packages.order_by('-created_at')
	has_filters_applied = any(
		[
			bool(search_query),
			selected_status != 'all',
			selected_active != 'all',
			selected_category != 'all',
		]
	)
	return render(
		request,
		'vendor/package_list.html',
		{
			'packages': packages,
			'vendor_profile': vendor_profile,
			'search_query': search_query,
			'selected_status': selected_status,
			'selected_active': selected_active,
			'selected_category': selected_category,
			'package_status_options': ApprovalStatus.choices,
			'package_category_options': Package.Category.choices,
			'has_filters_applied': has_filters_applied,
		},
	)


@login_required
def activity_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	search_query = request.GET.get('q', '').strip()
	selected_status = request.GET.get('status', 'all').upper()
	selected_active = request.GET.get('active', 'all').lower()
	selected_difficulty = request.GET.get('difficulty', 'all').lower()
	selected_category = request.GET.get('category', 'all')

	valid_statuses = {choice[0] for choice in ApprovalStatus.choices}
	valid_difficulty_levels = {choice[0] for choice in Activity.DifficultyLevel.choices}

	activities = Activity.objects.filter(vendor=vendor_profile).select_related('category')

	if search_query:
		activities = activities.filter(
			Q(name__icontains=search_query)
			| Q(description__icontains=search_query)
			| Q(category__name__icontains=search_query)
			| Q(equipment_provided__icontains=search_query)
			| Q(safety_notes__icontains=search_query)
		)

	if selected_status in valid_statuses:
		activities = activities.filter(approval_status=selected_status)
	else:
		selected_status = 'all'

	if selected_active == 'active':
		activities = activities.filter(is_active=True)
	elif selected_active == 'inactive':
		activities = activities.filter(is_active=False)
	else:
		selected_active = 'all'

	if selected_difficulty in valid_difficulty_levels:
		activities = activities.filter(difficulty_level=selected_difficulty)
	else:
		selected_difficulty = 'all'

	activity_category_options = ActivityCategory.objects.filter(activities__vendor=vendor_profile).distinct().order_by('name')
	if selected_category.isdigit():
		activities = activities.filter(category_id=int(selected_category))
	else:
		selected_category = 'all'

	activities = activities.order_by('name')
	has_filters_applied = any(
		[
			bool(search_query),
			selected_status != 'all',
			selected_active != 'all',
			selected_difficulty != 'all',
			selected_category != 'all',
		]
	)
	return render(
		request,
		'vendor/activity_list.html',
		{
			'activities': activities,
			'vendor_profile': vendor_profile,
			'search_query': search_query,
			'selected_status': selected_status,
			'selected_active': selected_active,
			'selected_difficulty': selected_difficulty,
			'selected_category': selected_category,
			'activity_status_options': ApprovalStatus.choices,
			'activity_difficulty_options': Activity.DifficultyLevel.choices,
			'activity_category_options': activity_category_options,
			'has_filters_applied': has_filters_applied,
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
				activity.approval_status = ApprovalStatus.PENDING
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
				activity = form.save()
				if activity.approval_status == ApprovalStatus.REJECTED:
					activity.approval_status = ApprovalStatus.PENDING
					activity.rejection_reason = None
					activity.save(update_fields=['approval_status', 'rejection_reason'])
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
def activity_availability(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	activity = get_object_or_404(Activity, pk=pk, vendor=vendor_profile)
	if request.method == 'POST' and request.POST.get('action') == 'delete':
		entry = get_object_or_404(ActivityUnavailableDate, pk=request.POST.get('entry_id'), activity=activity)
		entry.delete()
		messages.success(request, 'Blocked date removed for this activity.')
		return redirect('vendor:activity_availability', pk=activity.pk)

	if request.method == 'POST':
		form = VendorActivityUnavailableDateForm(request.POST)
		if form.is_valid():
			start_date = form.cleaned_data['date_from']
			end_date = form.cleaned_data['date_to']
			reason = (form.cleaned_data.get('reason') or '').strip()
			created_count = 0
			skipped_count = 0

			current_date = start_date
			while current_date <= end_date:
				_, created = ActivityUnavailableDate.objects.get_or_create(
					activity=activity,
					date=current_date,
					defaults={'reason': reason},
				)
				if created:
					created_count += 1
				else:
					skipped_count += 1
				current_date += timedelta(days=1)

			if created_count and skipped_count:
				messages.success(
					request,
					f'Blocked {created_count} day(s). {skipped_count} day(s) were already blocked.',
				)
			elif created_count:
				messages.success(request, f'Blocked {created_count} day(s) successfully for this activity.')
			else:
				messages.info(request, 'All selected dates were already blocked for this activity.')

			return redirect('vendor:activity_availability', pk=activity.pk)
	else:
		form = VendorActivityUnavailableDateForm()

	blocked_dates = activity.unavailable_dates.order_by('date')
	return render(
		request,
		'vendor/activity_availability.html',
		{
			'activity': activity,
			'form': form,
			'blocked_dates': blocked_dates,
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
				package.approval_status = ApprovalStatus.PENDING
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
		was_rejected_before_edit = package.approval_status == ApprovalStatus.REJECTED
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
				package = form.save()
				formset.save()
				if was_rejected_before_edit:
					package.approval_status = ApprovalStatus.PENDING
					package.rejection_reason = None
					package.save(update_fields=['approval_status', 'rejection_reason'])
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
def package_availability(request, pk):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	package = get_object_or_404(Package, pk=pk, vendor=vendor_profile)
	if request.method == 'POST' and request.POST.get('action') == 'delete':
		entry = get_object_or_404(PackageUnavailableDate, pk=request.POST.get('entry_id'), package=package)
		entry.delete()
		messages.success(request, 'Blocked date removed for this package.')
		return redirect('vendor:package_availability', pk=package.pk)

	if request.method == 'POST':
		form = VendorPackageUnavailableDateForm(request.POST)
		if form.is_valid():
			start_date = form.cleaned_data['date_from']
			end_date = form.cleaned_data['date_to']
			reason = (form.cleaned_data.get('reason') or '').strip()
			created_count = 0
			skipped_count = 0

			current_date = start_date
			while current_date <= end_date:
				_, created = PackageUnavailableDate.objects.get_or_create(
					package=package,
					date=current_date,
					defaults={'reason': reason},
				)
				if created:
					created_count += 1
				else:
					skipped_count += 1
				current_date += timedelta(days=1)

			if created_count and skipped_count:
				messages.success(
					request,
					f'Blocked {created_count} day(s). {skipped_count} day(s) were already blocked.',
				)
			elif created_count:
				messages.success(request, f'Blocked {created_count} day(s) successfully for this package.')
			else:
				messages.info(request, 'All selected dates were already blocked for this package.')

			return redirect('vendor:package_availability', pk=package.pk)
	else:
		form = VendorPackageUnavailableDateForm()

	blocked_dates = package.unavailable_dates.order_by('date')
	return render(
		request,
		'vendor/package_availability.html',
		{
			'package': package,
			'form': form,
			'blocked_dates': blocked_dates,
		},
	)


@login_required
def hot_sale_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	search_query = request.GET.get('q', '').strip()
	selected_type = request.GET.get('type', 'all').lower()
	selected_status = request.GET.get('status', 'all').lower()

	hot_sales = HotSale.objects.filter(
		Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile)
	).select_related('package', 'activity').prefetch_related('activity__images')

	if search_query:
		hot_sales = hot_sales.filter(
			Q(package__title__icontains=search_query)
			| Q(activity__name__icontains=search_query)
			| Q(note__icontains=search_query)
		)

	if selected_type == 'package':
		hot_sales = hot_sales.filter(package__isnull=False)
	elif selected_type == 'activity':
		hot_sales = hot_sales.filter(activity__isnull=False)
	else:
		selected_type = 'all'

	if selected_status == 'active':
		hot_sales = hot_sales.filter(is_active=True)
	elif selected_status == 'inactive':
		hot_sales = hot_sales.filter(is_active=False)
	else:
		selected_status = 'all'

	hot_sales = hot_sales.order_by('-created_at')
	has_filters_applied = any([
		bool(search_query),
		selected_type != 'all',
		selected_status != 'all',
	])
	return render(
		request,
		'vendor/hot_sale_list.html',
		{
			'hot_sales': hot_sales,
			'vendor_profile': vendor_profile,
			'search_query': search_query,
			'selected_type': selected_type,
			'selected_status': selected_status,
			'has_filters_applied': has_filters_applied,
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

	search_query = request.GET.get('q', '').strip()
	selected_reply = request.GET.get('reply', 'all').lower()
	selected_package = request.GET.get('package', 'all')

	package_options = Package.objects.filter(vendor=vendor_profile).order_by('title')

	inquiries = Inquiry.objects.filter(package__vendor=vendor_profile).select_related('package', 'user')

	if search_query:
		inquiries = inquiries.filter(
			Q(package__title__icontains=search_query)
			| Q(full_name__icontains=search_query)
			| Q(email__icontains=search_query)
			| Q(phone__icontains=search_query)
			| Q(message__icontains=search_query)
			| Q(admin_reply__icontains=search_query)
		)

	if selected_reply == 'replied':
		inquiries = inquiries.exclude(admin_reply='')
	elif selected_reply == 'pending':
		inquiries = inquiries.filter(admin_reply='')
	else:
		selected_reply = 'all'

	if selected_package.isdigit():
		inquiries = inquiries.filter(package_id=int(selected_package))
	else:
		selected_package = 'all'

	inquiries = inquiries.order_by('-created_at')

	if request.GET.get('export', '').lower() == 'csv':
		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename="vendor_inquiries.csv"'
		writer = csv.writer(response)
		writer.writerow([
			'ID',
			'Package',
			'Customer',
			'Email',
			'Phone',
			'Message',
			'Reply Status',
			'Created At',
		])
		for inquiry in inquiries:
			writer.writerow([
				inquiry.id,
				inquiry.package.title,
				inquiry.full_name,
				inquiry.email,
				inquiry.phone,
				inquiry.message,
				'Replied' if inquiry.admin_reply else 'Pending',
				inquiry.created_at.strftime('%Y-%m-%d %H:%M:%S'),
			])
		return response

	has_filters_applied = any([
		bool(search_query),
		selected_reply != 'all',
		selected_package != 'all',
	])

	export_query = request.GET.copy()
	export_query.pop('export', None)
	export_query['export'] = 'csv'

	return render(
		request,
		'vendor/inquiry_list.html',
		{
			'inquiries': inquiries,
			'vendor_profile': vendor_profile,
			'package_options': package_options,
			'search_query': search_query,
			'selected_reply': selected_reply,
			'selected_package': selected_package,
			'has_filters_applied': has_filters_applied,
			'export_query_string': export_query.urlencode(),
		},
	)


@login_required
def booking_list(request):
	vendor_profile = _get_approved_vendor_profile(request)
	if vendor_profile is None:
		return redirect('home')

	search_query = request.GET.get('q', '').strip()
	travel_from_input = request.GET.get('travel_from', '').strip()
	travel_to_input = request.GET.get('travel_to', '').strip()
	selected_payment_status = request.GET.get('payment_status', 'all').upper()
	selected_payment_method = request.GET.get('payment_method', 'all').upper()
	selected_sort = request.GET.get('sort', 'booked_desc')

	travel_from = None
	travel_to = None
	if travel_from_input:
		try:
			travel_from = date.fromisoformat(travel_from_input)
		except ValueError:
			travel_from_input = ''
	if travel_to_input:
		try:
			travel_to = date.fromisoformat(travel_to_input)
		except ValueError:
			travel_to_input = ''

	if travel_from and travel_to and travel_from > travel_to:
		travel_from, travel_to = travel_to, travel_from
		travel_from_input = travel_from.isoformat()
		travel_to_input = travel_to.isoformat()

	valid_payment_statuses = {choice[0] for choice in Booking.PaymentStatus.choices}
	valid_payment_methods = {choice[0] for choice in Booking.PaymentMethod.choices}

	bookings = (
		Booking.objects.visible_in_listings()
		.filter(package__vendor=vendor_profile)
		.select_related('package', 'package__destination', 'user')
	)

	if search_query:
		bookings = bookings.filter(
			Q(package__title__icontains=search_query)
			| Q(full_name__icontains=search_query)
			| Q(email__icontains=search_query)
			| Q(phone__icontains=search_query)
			| Q(transaction_reference__icontains=search_query)
			| Q(pickup_location__icontains=search_query)
			| Q(nationality__icontains=search_query)
		)

	if selected_payment_status in valid_payment_statuses:
		bookings = bookings.filter(payment_status=selected_payment_status)
	else:
		selected_payment_status = 'all'

	if selected_payment_method in valid_payment_methods:
		bookings = bookings.filter(payment_method=selected_payment_method)
	else:
		selected_payment_method = 'all'

	if travel_from:
		bookings = bookings.filter(travel_date__gte=travel_from)
	if travel_to:
		bookings = bookings.filter(travel_date__lte=travel_to)

	sort_options = [
		('booked_desc', 'Booked: Newest first'),
		('booked_asc', 'Booked: Oldest first'),
		('travel_asc', 'Travel date: Earliest first'),
		('travel_desc', 'Travel date: Latest first'),
		('amount_desc', 'Amount: High to low'),
		('amount_asc', 'Amount: Low to high'),
	]
	sort_ordering = {
		'booked_desc': ('-created_at', '-id'),
		'booked_asc': ('created_at', 'id'),
		'travel_asc': ('travel_date', '-created_at'),
		'travel_desc': ('-travel_date', '-created_at'),
		'amount_desc': ('-total_amount', '-created_at'),
		'amount_asc': ('total_amount', '-created_at'),
	}
	if selected_sort not in sort_ordering:
		selected_sort = 'booked_desc'

	bookings = bookings.order_by(*sort_ordering[selected_sort])

	if request.GET.get('export', '').lower() == 'csv':
		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename="vendor_bookings.csv"'
		writer = csv.writer(response)
		writer.writerow([
			'ID',
			'Package',
			'Traveler',
			'Email',
			'Phone',
			'Travel Date',
			'People',
			'Payment Status',
			'Payment Method',
			'Total Amount',
			'Booked On',
		])
		for booking in bookings:
			writer.writerow([
				booking.id,
				booking.package.title,
				booking.full_name,
				booking.email,
				booking.phone,
				booking.travel_date.isoformat() if booking.travel_date else '',
				booking.number_of_people,
				booking.get_payment_status_display(),
				booking.get_payment_method_display(),
				booking.total_amount,
				booking.created_at.strftime('%Y-%m-%d %H:%M:%S'),
			])
		return response

	paginator = Paginator(bookings, 12)
	page_obj = paginator.get_page(request.GET.get('page'))
	bookings = page_obj.object_list

	base_query = request.GET.copy()
	base_query.pop('page', None)
	base_query.pop('export', None)
	pagination_query_string = base_query.urlencode()

	export_query = base_query.copy()
	export_query['export'] = 'csv'
	has_filters_applied = any(
		[
			bool(search_query),
			selected_payment_status != 'all',
			selected_payment_method != 'all',
			bool(travel_from_input),
			bool(travel_to_input),
		]
	)
	return render(
		request,
		'vendor/booking_list.html',
		{
			'bookings': bookings,
			'page_obj': page_obj,
			'vendor_profile': vendor_profile,
			'search_query': search_query,
			'selected_travel_from': travel_from_input,
			'selected_travel_to': travel_to_input,
			'selected_payment_status': selected_payment_status,
			'selected_payment_method': selected_payment_method,
			'selected_sort': selected_sort,
			'payment_status_options': Booking.PaymentStatus.choices,
			'payment_method_options': Booking.PaymentMethod.choices,
			'sort_options': sort_options,
			'pagination_query_string': pagination_query_string,
			'export_query_string': export_query.urlencode(),
			'has_filters_applied': has_filters_applied,
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
