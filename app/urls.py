from . import views
from django.urls import path
from django.views.generic.base import RedirectView
from .views import signup_view, login_view, logout_view, destination_list

urlpatterns = [
    # path("", RedirectView.as_view(pattern_name='login', permanent=False), name='root'),
    path("signup/", signup_view, name="signup"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("", views.home, name='home'),
    path('destinations/', destination_list, name='destination_list'),
     path("destinations/<int:pk>/", views.destination_detail, name="destination_detail"),
]


