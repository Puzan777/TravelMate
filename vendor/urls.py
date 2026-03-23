from django.urls import path

from . import views

app_name = 'vendor'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
]
