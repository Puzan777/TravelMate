
# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .forms import SignUpForm, LoginForm
from .models import Destination

def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()      #  password hashed automatically
            login(request, user)    #  auto login after signup
            return redirect("home")
    else:
        form = SignUpForm()
    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("home")
    else:
        form = LoginForm()
    return render(request, "login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")

def home(request):
    featured_destinations = Destination.objects.filter(
        is_featured=True,
        is_active=True
    )[:6]  # limit to 6

    return render(request, "home.html", {
        "featured_destinations": featured_destinations
    })

def destination_list(request):
    destinations = Destination.objects.filter(is_active=True)
    return render(request, 'destination_list.html', {
        'destinations': destinations
    })

def destination_detail(request, pk):
    destination = Destination.objects.get(pk=pk)
    return render(request, 'destination_detail.html', {
        'destination': destination
    })
