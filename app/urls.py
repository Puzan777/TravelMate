from . import views
from django.urls import path
from django.views.generic.base import RedirectView
from .views import signup_view, login_view, logout_view, destination_list, forgot_password, verify_reset_otp, reset_password

urlpatterns = [
    # path("", RedirectView.as_view(pattern_name='login', permanent=False), name='root'),
    path("signup/", signup_view, name="signup"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("forgot-password/", forgot_password, name="forgot_password"),
    path("verify-reset-otp/", verify_reset_otp, name="verify_reset_otp"),
    path("reset-password/", reset_password, name="reset_password"),
    path('profile/', views.profile_view, name='profile'),
    path("", views.home, name='home'),

    # Search
    path('search/', views.search_view, name='search'),
    path('search/suggestions/', views.search_suggestions, name='search_suggestions'),

    # Destinations
    path('destinations/', destination_list, name='destination_list'),
    path("destinations/<int:pk>/", views.destination_detail, name="destination_detail"),

    # Activities
    path('activities/', views.activity_list_view, name='activity_list'),
    path('activities/<int:pk>/favorite/', views.toggle_favorite_activity, name='toggle_favorite_activity'),
    path('activities/<int:pk>/', views.activity_detail, name='activity_detail'),

    # Vendors
    path('vendors/', views.vendor_showcase, name='vendor_showcase'),

    # Packages
    path('packages/standard/', views.package_list, {'category': 'STANDARD'}, name='packages_standard'),
    path('packages/luxury/', views.package_list, {'category': 'LUXURY'}, name='packages_luxury'),
    path('packages/trekking/', views.package_list, {'category': 'TREKKING'}, name='packages_trekking'),
    path('packages/heli/', views.package_list, {'category': 'HELI'}, name='packages_heli'),
    path('packages/hot-sales/', views.hot_sale_list, name='packages_hot_sales'),

    # Payments
    path('payments/esewa/callback/', views.esewa_callback, name='esewa_callback'),
    path('payments/esewa/failure/', views.esewa_failure, name='esewa_failure'),

    # Package detail must come last (after specific package pages)
    path('packages/<slug:slug>/favorite/', views.toggle_favorite_package, name='toggle_favorite_package'),
    path('packages/<slug:slug>/', views.package_detail, name='package_detail'),
]
