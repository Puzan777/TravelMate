# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils import timezone
from .forms import SignUpForm, LoginForm, BookingForm
from .models import Destination, Package, Booking


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
        qs = qs.filter(is_hot_sale=True)
        title = 'Hot Sales'
    elif category:
        qs = qs.filter(category=category)
        title = dict(Package.Category.choices).get(category, category.title())

    return render(request, 'packages_list.html', {
        'packages': qs,
        'category': category,
        'hot_sales': hot_sales,
        'title': title,
    })


def package_detail(request, slug):
    package = get_object_or_404(Package, slug=slug, is_active=True)

    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect('login')

        form = BookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.package = package
            booking.user = request.user
            booking.save()
            messages.success(request, 'Your booking request has been submitted successfully.')
            return redirect('package_detail', slug=slug)
    else:
        form = BookingForm(initial={'travel_date': timezone.localdate()})

    return render(request, 'package_detail.html', {
        'package': package,
        'booking_form': form,
    })
