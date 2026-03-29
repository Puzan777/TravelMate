from datetime import date

from django import template
from django.db.models import Count
from django.db.models.functions import TruncMonth

from app.models import Booking, CustomUser, Destination, HotSale, Inquiry, Package

try:
    from vendor.models import VendorProfile
except Exception:  # pragma: no cover - keeps admin dashboard resilient
    VendorProfile = None

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
def dashboard_inquiry_count():
    return Inquiry.objects.count()


@register.simple_tag
def dashboard_replied_inquiry_count():
    return Inquiry.objects.exclude(admin_reply='').exclude(admin_reply__isnull=True).count()


@register.simple_tag
def dashboard_inquiry_reply_rate():
    total = Inquiry.objects.count()
    if total == 0:
        return 0
    replied = dashboard_replied_inquiry_count()
    return round((replied / total) * 100)


@register.simple_tag
def dashboard_hot_sale_count():
    return HotSale.objects.count()


@register.simple_tag
def dashboard_pending_vendor_count():
    if VendorProfile is None:
        return 0
    return VendorProfile.objects.filter(verification_status=VendorProfile.VerificationStatus.PENDING).count()


@register.simple_tag
def dashboard_approved_vendor_count():
    if VendorProfile is None:
        return 0
    return VendorProfile.objects.filter(verification_status=VendorProfile.VerificationStatus.APPROVED).count()


@register.simple_tag
def dashboard_recent_bookings(limit=5):
    return Booking.objects.select_related('package', 'user').order_by('-created_at')[:limit]


@register.simple_tag
def dashboard_recent_users(limit=5):
    return CustomUser.objects.order_by('-date_joined')[:limit]


@register.simple_tag
def dashboard_hot_sale_packages(limit=6):
    return HotSale.objects.select_related('package', 'package__destination').order_by('-updated_at')[:limit]


@register.simple_tag
def dashboard_recent_inquiries(limit=6):
    return Inquiry.objects.select_related('package', 'user').order_by('-created_at')[:limit]


@register.simple_tag
def dashboard_recent_vendor_applications(limit=6):
    if VendorProfile is None:
        return []
    return VendorProfile.objects.select_related('user').order_by('-submitted_at')[:limit]


@register.simple_tag
def dashboard_top_packages(limit=5):
    return (
        Package.objects
        .select_related('destination', 'vendor')
        .annotate(total_bookings=Count('bookings'))
        .order_by('-total_bookings', 'title')[:limit]
    )


@register.simple_tag
def dashboard_monthly_bookings(months=6):
    months = max(int(months), 1)

    today = date.today()
    month_cursor = date(today.year, today.month, 1)
    labels = []
    keys = []

    for _ in range(months):
        keys.append((month_cursor.year, month_cursor.month))
        labels.append(month_cursor.strftime('%b %Y'))
        if month_cursor.month == 1:
            month_cursor = date(month_cursor.year - 1, 12, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month - 1, 1)

    keys.reverse()
    labels.reverse()
    start_year, start_month = keys[0]
    start_date = date(start_year, start_month, 1)

    monthly_data = (
        Booking.objects
        .filter(created_at__date__gte=start_date)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Count('id'))
    )

    counts_by_key = {(row['month'].year, row['month'].month): row['total'] for row in monthly_data}

    return [
        {'label': label, 'total': counts_by_key.get(key, 0)}
        for label, key in zip(labels, keys)
    ]
