from django.urls import path

from . import views

app_name = 'vendor'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/<int:pk>/', views.booking_detail, name='booking_detail'),
    path('activities/', views.activity_list, name='activity_list'),
    path('activities/create/', views.activity_create, name='activity_create'),
    path('activities/<int:pk>/view/', views.activity_detail, name='activity_detail'),
    path('activities/<int:pk>/edit/', views.activity_edit, name='activity_edit'),
    path('activities/<int:pk>/delete/', views.activity_delete, name='activity_delete'),
    path('activities/<int:pk>/availability/', views.activity_availability, name='activity_availability'),
    path('packages/', views.package_list, name='package_list'),
    path('packages/create/', views.package_create, name='package_create'),
    path('packages/<int:pk>/view/', views.package_detail, name='package_detail'),
    path('packages/<int:pk>/edit/', views.package_edit, name='package_edit'),
    path('packages/<int:pk>/availability/', views.package_availability, name='package_availability'),
    path('hot-sales/', views.hot_sale_list, name='hot_sale_list'),
    path('hot-sales/create/', views.hot_sale_create, name='hot_sale_create'),
    path('hot-sales/<int:pk>/edit/', views.hot_sale_edit, name='hot_sale_edit'),
    path('hot-sales/<int:pk>/delete/', views.hot_sale_delete, name='hot_sale_delete'),
    path('inquiries/', views.inquiry_list, name='inquiry_list'),
    path('inquiries/<int:pk>/reply/', views.inquiry_reply, name='inquiry_reply'),
]
