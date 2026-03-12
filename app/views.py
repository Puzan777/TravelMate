# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, LoginForm, BookingForm, InquiryForm
from .models import Destination, Package, Booking, Inquiry, HotSale


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()      #  password hashed automatically
            login(request, user)    #  auto login after signup
            if user.is_staff or user.is_superuser:
                return redirect("/admin/")
            return redirect("home")
    else:
        form = SignUpForm()
    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('/admin/')
        return redirect('home')

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_staff or user.is_superuser:
                return redirect('/admin/')
            return redirect("home")
    else:
        form = LoginForm()
    return render(request, "login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


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
        package__is_active=True,
    ).select_related('package', 'package__destination')

    return render(request, 'hot_sales.html', {
        'hot_sales': hot_sales,
        'title': 'Hot Sales',
    })


def package_detail(request, slug):
    package = get_object_or_404(Package, slug=slug, is_active=True)
    is_favorite = False

    if request.user.is_authenticated:
        is_favorite = request.user.favorite_packages.filter(pk=package.pk).exists()

    booking_initial = {'travel_date': timezone.localdate()}
    inquiry_initial = {}
    if request.user.is_authenticated:
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
    })


@login_required
def profile_view(request):
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
