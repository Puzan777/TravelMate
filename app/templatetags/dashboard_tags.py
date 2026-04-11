from datetime import date

from django import template
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from django.db.models.functions import TruncMonth

from app.models import Activity, ApprovalStatus, Booking, CustomUser, Destination, HotSale, Inquiry, Package

try:
    from vendor.models import VendorProfile
except Exception:  # pragma: no cover - keeps admin dashboard resilient
    VendorProfile = None

register = template.Library()


@register.simple_tag
def dashboard_package_count():
    return Package.objects.count()


@register.simple_tag
def dashboard_pending_product_count():
    pending_packages = Package.objects.filter(approval_status=ApprovalStatus.PENDING).count()
    pending_activities = Activity.objects.filter(approval_status=ApprovalStatus.PENDING).count()
    return pending_packages + pending_activities

@register.simple_tag
def dashboard_live_product_count():
    live_packages = Package.objects.filter(approval_status=ApprovalStatus.APPROVED, is_active=True).count()
    live_activities = Activity.objects.filter(approval_status=ApprovalStatus.APPROVED, is_active=True).count()
    return live_packages + live_activities


@register.simple_tag
def dashboard_active_package_count():
    return Package.objects.filter(is_active=True).count()


@register.simple_tag
def dashboard_pending_product_count():
    pending_packages = Package.objects.filter(approval_status=ApprovalStatus.PENDING).count()
    pending_activities = Activity.objects.filter(approval_status=ApprovalStatus.PENDING).count()
    return pending_packages + pending_activities

@register.simple_tag
def dashboard_live_product_count():
    live_packages = Package.objects.filter(approval_status=ApprovalStatus.APPROVED, is_active=True).count()
    live_activities = Activity.objects.filter(approval_status=ApprovalStatus.APPROVED, is_active=True).count()
    return live_packages + live_activities


@register.simple_tag
def dashboard_activity_count():
    return Activity.objects.count()


@register.simple_tag
def dashboard_active_activity_count():
    return Activity.objects.filter(is_active=True).count()


@register.simple_tag
def dashboard_destination_count():
    return Destination.objects.count()


@register.simple_tag
def dashboard_booking_count():
    return Booking.objects.visible_in_listings().count()


@register.simple_tag
def dashboard_user_count():
    return CustomUser.objects.count()


@register.simple_tag
def dashboard_customer_count():
    return CustomUser.objects.filter(role=CustomUser.Role.CUSTOMER).count()


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
def dashboard_favorite_count():
    return CustomUser.favorite_packages.through.objects.count()


@register.simple_tag
def dashboard_hot_sale_breakdown():
    package_count = HotSale.objects.filter(package__isnull=False).count()
    activity_count = HotSale.objects.filter(activity__isnull=False).count()
    return {
        'total': package_count + activity_count,
        'packages': package_count,
        'activities': activity_count,
    }


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
def dashboard_vendor_count():
    if VendorProfile is None:
        return 0
    return VendorProfile.objects.count()


@register.simple_tag
def dashboard_total_revenue():
    total = Booking.objects.visible_in_listings().aggregate(total=Sum('total_amount'))['total']
    return total or 0


@register.simple_tag
def dashboard_recent_bookings(limit=5):
    return Booking.objects.visible_in_listings().select_related('package', 'user').order_by('-created_at')[:limit]


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
        .annotate(total_bookings=Count('bookings', filter=Booking.visible_in_listings_q(prefix='bookings__')))
        .order_by('-total_bookings', 'title')[:limit]
    )


@register.simple_tag
def dashboard_top_activities(limit=5):
    return (
        Activity.objects
        .select_related('vendor', 'category')
        .annotate(total_hot_sales=Count('hot_sale_entries'))
        .order_by('-total_hot_sales', 'name')[:limit]
    )


@register.simple_tag
def dashboard_top_products(limit=10):
    limit = max(int(limit), 1)

    package_rows = (
        Package.objects
        .select_related('vendor')
        .annotate(total_bookings=Count('bookings', filter=Booking.visible_in_listings_q(prefix='bookings__')))
        .values('title', 'vendor__company_name', 'total_bookings', 'rating')
    )

    activity_rows = (
        Activity.objects
        .select_related('vendor')
        .values('name', 'vendor__company_name')
    )

    rows = []
    for row in package_rows:
        rows.append({
            'product_name': row['title'],
            'product_type': 'Package',
            'vendor_name': row['vendor__company_name'] or '-',
            'bookings': row['total_bookings'] or 0,
            'rating_display': f"{row['rating']:.1f}" if row['rating'] is not None else '-',
        })

    for row in activity_rows:
        rows.append({
            'product_name': row['name'],
            'product_type': 'Activity',
            'vendor_name': row['vendor__company_name'] or '-',
            # Activity bookings are not modeled yet in Booking, so keep at zero.
            'bookings': 0,
            'rating_display': '-',
        })

    rows.sort(key=lambda item: (-item['bookings'], item['product_name'].lower()))
    return rows[:limit]


@register.simple_tag
def dashboard_product_trends(months=6):
    months = max(int(months), 1)

    today = date.today()
    month_cursor = date(today.year, today.month, 1)
    keys = []
    labels = []

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

    package_monthly = (
        Booking.objects.visible_in_listings()
        .filter(created_at__date__gte=start_date)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Count('id'))
    )
    package_map = {(row['month'].year, row['month'].month): row['total'] for row in package_monthly}

    points = []
    for label, key in zip(labels, keys):
        package_total = package_map.get(key, 0)
        activity_total = 0
        points.append({
            'label': label,
            'package_bookings': package_total,
            'activity_bookings': activity_total,
        })

    return {
        'points': points,
        'total_package_bookings': sum(point['package_bookings'] for point in points),
        'total_activity_bookings': sum(point['activity_bookings'] for point in points),
    }


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
        Booking.objects.visible_in_listings()
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


@register.simple_tag
def dashboard_monthly_revenue():
    now = timezone.now()
    bookings = Booking.objects.visible_in_listings().filter(
        created_at__year=now.year, created_at__month=now.month
    )
    total = bookings.aggregate(total=Sum('total_amount'))['total']
    return total or 0


@register.simple_tag
def dashboard_monthly_booking_count():
    now = timezone.now()
    return Booking.objects.visible_in_listings().filter(
        created_at__year=now.year, created_at__month=now.month
    ).count()


@register.simple_tag
def dashboard_average_platform_rating():
    pkg_avg = Package.objects.filter(is_active=True).aggregate(avg=Avg('rating'))['avg']
    return round(float(pkg_avg), 1) if pkg_avg is not None else 0.0

