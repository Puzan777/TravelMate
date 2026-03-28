from django.urls import path

from . import views

app_name = 'vendor'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('destinations/', views.destination_list, name='destination_list'),
    path('destinations/create/', views.destination_create, name='destination_create'),
    path('destinations/<int:pk>/edit/', views.destination_edit, name='destination_edit'),
    path('packages/', views.package_list, name='package_list'),
    path('packages/create/', views.package_create, name='package_create'),
    path('packages/<int:pk>/edit/', views.package_edit, name='package_edit'),
    path('hot-sales/', views.hot_sale_list, name='hot_sale_list'),
    path('hot-sales/create/', views.hot_sale_create, name='hot_sale_create'),
    path('hot-sales/<int:pk>/edit/', views.hot_sale_edit, name='hot_sale_edit'),
    path('inquiries/', views.inquiry_list, name='inquiry_list'),
    path('inquiries/<int:pk>/reply/', views.inquiry_reply, name='inquiry_reply'),
]
