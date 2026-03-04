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
