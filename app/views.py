# Create your views here.
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .forms import ActivityCategoryForm, SignUpForm, LoginForm, BookingForm, InquiryForm
from .models import ActivityCategory, Booking, CustomUser, Destination, HotSale, Inquiry, Package


def _redirect_after_login(request, user):
    if user.is_staff or user.is_superuser or user.role == CustomUser.Role.ADMIN:
        return redirect('/admin/')
    if user.role == CustomUser.Role.VENDOR:
        from vendor.models import VendorProfile

        profile = VendorProfile.objects.filter(user=user).first()
        if profile and profile.verification_status == VendorProfile.VerificationStatus.APPROVED:
            return redirect('vendor:dashboard')
        if profile and profile.verification_status == VendorProfile.VerificationStatus.REJECTED and profile.rejection_reason:
            messages.error(request, f'Your vendor account was rejected: {profile.rejection_reason}')
            return redirect('home')
        messages.warning(request, 'Your vendor registration is pending approval.')
        return redirect('home')
    return redirect('home')


def _ensure_vendor_profile(user):
    if user.role != CustomUser.Role.VENDOR:
        return
    from vendor.models import VendorProfile

    VendorProfile.objects.get_or_create(
        user=user,
        defaults={
            'company_name': user.get_full_name() or user.username,
        },
    )


def _ensure_platform_admin(user):
    is_platform_admin = user.is_authenticated and (
        user.is_superuser or user.role == CustomUser.Role.ADMIN or (user.is_staff and not user.is_vendor)
    )
    if not is_platform_admin:
        raise PermissionDenied


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()      #  password hashed automatically
            login(request, user)    #  auto login after signup
            return _redirect_after_login(request, user)
    else:
        form = SignUpForm()
    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_after_login(request, request.user)

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            _ensure_vendor_profile(user)
            return _redirect_after_login(request, user)
    else:
        form = LoginForm()
    return render(request, "login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def activity_category_list(request):
    _ensure_platform_admin(request.user)
    categories = ActivityCategory.objects.order_by('name')
    return render(request, 'admin_portal/activity_category_list.html', {'categories': categories})


@login_required
def activity_category_create(request):
    _ensure_platform_admin(request.user)
    if request.method == 'POST':
        form = ActivityCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Activity category created successfully.')
            return redirect('activity_category_list')
    else:
        form = ActivityCategoryForm()
    return render(
        request,
        'admin_portal/activity_category_form.html',
        {
            'form': form,
            'page_title': 'Create Activity Category',
            'submit_label': 'Create Category',
        },
    )


@login_required
def activity_category_edit(request, pk):
    _ensure_platform_admin(request.user)
    category = get_object_or_404(ActivityCategory, pk=pk)
    if request.method == 'POST':
        form = ActivityCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Activity category updated successfully.')
            return redirect('activity_category_list')
    else:
        form = ActivityCategoryForm(instance=category)
    return render(
        request,
        'admin_portal/activity_category_form.html',
        {
            'form': form,
            'page_title': 'Edit Activity Category',
            'submit_label': 'Save Changes',
            'category': category,
        },
    )


@login_required
def activity_category_delete(request, pk):
    _ensure_platform_admin(request.user)
    category = get_object_or_404(ActivityCategory, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Activity category deleted successfully.')
        return redirect('activity_category_list')
    return render(request, 'admin_portal/activity_category_confirm_delete.html', {'category': category})


def home(request):
    # Show all destinations (countries)
    destinations = Destination.objects.all()[:6]  # limit to 6
    
    # Show active packages (best packages)
    packages = Package.objects.filter(is_active=True)[:6]  # limit to 6

    return render(request, "home.html", {
        "featured_destinations": destinations,
        "featured_packages": packages
    })


def destination_list(request):
    # Show all destinations (countries)
    destinations = Destination.objects.all()
    return render(request, 'destination_list.html', {
        'destinations': destinations
    })


def destination_detail(request, pk):
    # Get destination regardless of active status
    destination = get_object_or_404(Destination, pk=pk)
    # Get only active packages for this destination (country)
    packages = Package.objects.filter(
        destination=destination,
        is_active=True
    ).order_by('-created_at')
    
    return render(request, 'destination_detail.html', {
        'destination': destination,
        'packages': packages
    })


# ----------------- Package views -----------------
def package_list(request, category=None, hot_sales=False):
    qs = Package.objects.filter(is_active=True)
    title = 'Packages'

    if hot_sales:
        qs = qs.none()
        title = 'Packages'
    elif category:
        qs = qs.filter(category=category)
        title = dict(Package.Category.choices).get(category, category.title())

    return render(request, 'packages_list.html', {
        'packages': qs,
        'category': category,
        'hot_sales': hot_sales,
        'title': title,
    })


def hot_sale_list(request):
    hot_sales = HotSale.objects.filter(
        is_active=True,
    ).filter(
        Q(package__is_active=True) | Q(activity__is_active=True),
    ).select_related('package', 'package__destination', 'activity').prefetch_related('activity__images')

    return render(request, 'hot_sales.html', {
        'hot_sales': hot_sales,
        'title': 'Hot Sales',
    })


def package_detail(request, slug):
    package = get_object_or_404(
        Package.objects.prefetch_related('itinerary_entries'),
        slug=slug,
        is_active=True,
    )
    is_favorite = False
    itinerary_days = list(package.itinerary_entries.all())

    if request.user.is_authenticated:
        is_favorite = request.user.favorite_packages.filter(pk=package.pk).exists()

    booking_initial = {'travel_date': timezone.localdate(), 'number_of_people': 1}
    inquiry_initial = {}
    if request.user.is_authenticated:
        booking_initial.update({
            'full_name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
        })
        inquiry_initial = {
            'full_name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
        }

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'booking':
            if not request.user.is_authenticated:
                return redirect('login')

            booking_form = BookingForm(request.POST)
            inquiry_form = InquiryForm(initial=inquiry_initial)
            if booking_form.is_valid():
                booking = booking_form.save(commit=False)
                booking.package = package
                booking.user = request.user
                booking.save()
                messages.success(request, 'Your booking request has been submitted successfully.')
                return redirect('package_detail', slug=slug)
        elif form_type == 'inquiry':
            booking_form = BookingForm(initial=booking_initial)
            inquiry_form = InquiryForm(request.POST)
            if inquiry_form.is_valid():
                inquiry = inquiry_form.save(commit=False)
                inquiry.package = package
                if request.user.is_authenticated:
                    inquiry.user = request.user
                inquiry.save()
                messages.success(request, 'Your inquiry has been sent. Our team will contact you soon.')
                return redirect('package_detail', slug=slug)
        else:
            booking_form = BookingForm(initial=booking_initial)
            inquiry_form = InquiryForm(initial=inquiry_initial)
    else:
        booking_form = BookingForm(initial=booking_initial)
        inquiry_form = InquiryForm(initial=inquiry_initial)

    return render(request, 'package_detail.html', {
        'package': package,
        'booking_form': booking_form,
        'inquiry_form': inquiry_form,
        'is_favorite': is_favorite,
        'itinerary_days': itinerary_days,
    })


@login_required
def profile_view(request):
    if request.user.role == CustomUser.Role.VENDOR:
        return redirect('vendor:dashboard')

    bookings = Booking.objects.filter(user=request.user).select_related('package', 'package__destination').order_by('-created_at')
    inquiries = Inquiry.objects.filter(user=request.user).select_related('package').order_by('-created_at')
    favorite_packages = request.user.favorite_packages.filter(is_active=True).select_related('destination').order_by('-updated_at')

    return render(request, 'profile.html', {
        'bookings': bookings,
        'inquiries': inquiries,
        'favorite_packages': favorite_packages,
    })


@login_required
def toggle_favorite_package(request, slug):
    if request.method != 'POST':
        return redirect('package_detail', slug=slug)

    package = get_object_or_404(Package, slug=slug, is_active=True)
    if request.user.favorite_packages.filter(pk=package.pk).exists():
        request.user.favorite_packages.remove(package)
        messages.info(request, 'Removed from favorites.')
    else:
        request.user.favorite_packages.add(package)
        messages.success(request, 'Added to favorites.')

    next_url = request.POST.get('next')
    if next_url == 'profile':
        return redirect('profile')
    return redirect('package_detail', slug=slug)
