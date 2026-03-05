from django import template
from app.models import Package, Destination, Booking, CustomUser

register = template.Library()


@register.simple_tag
def dashboard_package_count():
    return Package.objects.count()


@register.simple_tag
def dashboard_active_package_count():
    return Package.objects.filter(is_active=True).count()


@register.simple_tag
def dashboard_destination_count():
    return Destination.objects.count()


@register.simple_tag
def dashboard_booking_count():
    return Booking.objects.count()


@register.simple_tag
def dashboard_user_count():
    return CustomUser.objects.count()


@register.simple_tag
def dashboard_recent_bookings(limit=5):
    return Booking.objects.select_related('package', 'user').order_by('-created_at')[:limit]


@register.simple_tag
def dashboard_recent_users(limit=5):
    return CustomUser.objects.order_by('-date_joined')[:limit]


@register.simple_tag
def dashboard_hot_sale_packages(limit=6):
    return Package.objects.select_related('destination').filter(is_hot_sale=True).order_by('-updated_at')[:limit]
