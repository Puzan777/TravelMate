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

    # Destinations
    path('destinations/', destination_list, name='destination_list'),
    path("destinations/<int:pk>/", views.destination_detail, name="destination_detail"),

    # Packages
    path('packages/luxury/', views.package_list, {'category': 'LUXURY'}, name='packages_luxury'),
    path('packages/trekking/', views.package_list, {'category': 'TREKKING'}, name='packages_trekking'),
    path('packages/heli/', views.package_list, {'category': 'HELI'}, name='packages_heli'),
    path('packages/hot-sales/', views.package_list, {'hot_sales': True}, name='packages_hot_sales'),

    # package detail must come last (after specific package pages)
    path('packages/<int:pk>/', views.package_detail, name='package_detail'),
]


