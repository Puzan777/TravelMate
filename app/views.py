# Create your views here.
import base64
import binascii
import hashlib
import hmac
import json
import re
from functools import wraps
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from .forms import (
    ActivityBookingForm,
    ActivityCategoryForm,
    ActivityReviewForm,
    BookingForm,
    InquiryForm,
    LoginForm,
    PackageReviewForm,
    SignUpForm,
)
from .models import (
    Activity,
    ActivityBooking,
    ActivityCategory,
    ActivityReview,
    ApprovalStatus,
    Booking,
    CustomUser,
    Destination,
    HotSale,
    Inquiry,
    Package,
    PackageReview,
)


def _request_param(request, name):
    return request.POST.get(name) or request.GET.get(name)


def _is_hot_sale_context(request):
    return str(_request_param(request, 'hot_sale') or '').strip().lower() in {'1', 'true', 'yes'}


def _is_customer_user(user):
    return (
        user.is_authenticated
        and user.role == CustomUser.Role.CUSTOMER
        and not user.is_staff
        and not user.is_superuser
    )


def _favorite_card_context(request):
    can_toggle_favorites = _is_customer_user(request.user) if request.user.is_authenticated else False
    favorite_package_ids = set()
    favorite_activity_ids = set()

    if can_toggle_favorites:
        favorite_package_ids = set(request.user.favorite_packages.values_list('id', flat=True))
        favorite_activity_ids = set(request.user.favorite_activities.values_list('id', flat=True))

    return {
        'can_toggle_favorites': can_toggle_favorites,
        'favorite_package_ids': favorite_package_ids,
        'favorite_activity_ids': favorite_activity_ids,
    }


def _safe_next_redirect(request, fallback_response):
    next_url = (request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return fallback_response


def customer_only(view_func=None, *, error_message='Only customers can book packages.'):
    def decorator(func):
        @wraps(func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated and not _is_customer_user(request.user):
                messages.error(request, error_message)
                return redirect(request.META.get('HTTP_REFERER') or reverse('home'))
            return func(request, *args, **kwargs)

        return _wrapped_view

    if view_func is None:
        return decorator
    return decorator(view_func)


@customer_only
def _ensure_customer_booking_access(request):
    return None


@customer_only(error_message='Only customers can send inquiries.')
def _ensure_customer_inquiry_access(request):
    return None


def _can_user_review_package(user, package):
    if not user.is_authenticated:
        return False
    return Booking.objects.filter(user=user, package=package).visible_in_listings().exists()


def _can_user_review_activity(user, activity):
    if not user.is_authenticated:
        return False
    return ActivityBooking.objects.filter(user=user, activity=activity).visible_in_listings().exists()


def _extract_booking_target_from_token(token):
    if token is None:
        return None, None

    value = str(token).strip()
    if not value:
        return None, None

    if value.isdigit():
        return 'package', int(value)

    match = re.search(r'(\d+)$', value)
    if not match:
        return None, None

    token_upper = value.upper()
    if token_upper.startswith('ACTIVITY-BOOKING-') or token_upper.startswith('ACTIVITYBOOKING-'):
        return 'activity', int(match.group(1))
    return 'package', int(match.group(1))


def _parse_decimal_amount(value):
    if value in (None, ''):
        return None

    try:
        amount = Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        return None

    return amount.quantize(Decimal('0.01'))


def _is_external_http_url(url):
    parsed = urlparse(str(url or '').strip())
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _decode_esewa_data_blob(encoded_data):
    if not encoded_data:
        return {}

    padded = encoded_data + ('=' * (-len(encoded_data) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
        payload = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}

    if isinstance(payload, dict):
        return payload
    return {}


def _read_esewa_callback_payload(request):
    data_blob = _request_param(request, 'data')
    parsed_blob = _decode_esewa_data_blob(data_blob)

    booking_token = (
        _request_param(request, 'oid')
        or _request_param(request, 'pid')
        or parsed_blob.get('transaction_uuid')
        or parsed_blob.get('product_id')
    )

    return {
        'booking_token': booking_token,
        'amount': (
            _request_param(request, 'amt')
            or _request_param(request, 'total_amount')
            or parsed_blob.get('total_amount')
            or parsed_blob.get('amount')
        ),
        'reference': (
            _request_param(request, 'refId')
            or _request_param(request, 'transaction_code')
            or parsed_blob.get('transaction_code')
            or parsed_blob.get('reference_id')
        ),
        'status': (
            _request_param(request, 'status')
            or parsed_blob.get('status')
            or parsed_blob.get('transaction_status')
            or ''
        ),
        'product_code': (
            _request_param(request, 'scd')
            or parsed_blob.get('product_code')
            or parsed_blob.get('merchant_code')
            or ''
        ),
    }


def _send_new_booking_emails(booking):
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
        or 'no-reply@travelmate.local'
    )

    package_title = booking.package.title
    travel_date = booking.travel_date.strftime('%Y-%m-%d')
    amount = booking.total_amount
    payment_method = booking.get_payment_method_display()
    customer_name = booking.full_name

    customer_email = (booking.email or '').strip()
    vendor_email = ''
    vendor_profile = getattr(booking.package, 'vendor', None)
    if vendor_profile and vendor_profile.user:
        vendor_email = (vendor_profile.user.email or '').strip()

    if customer_email:
        customer_subject = f'Booking Confirmation - {package_title}'
        customer_message = (
            f'Hello {customer_name},\n\n'
            f'Your booking request has been received for {package_title}.\n\n'
            f'Travel date: {travel_date}\n'
            f'Number of people: {booking.number_of_people}\n'
            f'Payment method: {payment_method}\n'
            f'Total amount: {amount}\n\n'
            'We will contact you if any additional details are needed.\n\n'
            'Thank you,\n'
            'TravelMate Team'
        )
        send_mail(
            customer_subject,
            customer_message,
            from_email,
            [customer_email],
            fail_silently=True,
        )

    if vendor_email:
        vendor_subject = f'New Booking Alert - {package_title}'
        vendor_message = (
            'Hello,\n\n'
            f'You have received a new booking for {package_title}.\n\n'
            f'Traveler: {customer_name}\n'
            f'Email: {booking.email}\n'
            f'Phone: {booking.phone}\n'
            f'Travel date: {travel_date}\n'
            f'People: {booking.number_of_people}\n'
            f'Payment method: {payment_method}\n'
            f'Total amount: {amount}\n\n'
            'Please check your vendor dashboard for full details.\n\n'
            'TravelMate System'
        )
        send_mail(
            vendor_subject,
            vendor_message,
            from_email,
            [vendor_email],
            fail_silently=True,
        )


def _send_new_activity_booking_emails(activity_booking):
    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
        or 'no-reply@travelmate.local'
    )

    activity_name = activity_booking.activity.name
    travel_date = activity_booking.travel_date.strftime('%Y-%m-%d')
    amount = activity_booking.total_amount
    payment_method = activity_booking.get_payment_method_display()
    customer_name = activity_booking.full_name

    customer_email = (activity_booking.email or '').strip()
    vendor_email = ''
    vendor_profile = getattr(activity_booking.activity, 'vendor', None)
    if vendor_profile and vendor_profile.user:
        vendor_email = (vendor_profile.user.email or '').strip()

    if customer_email:
        customer_subject = f'Activity Booking Confirmation - {activity_name}'
        customer_message = (
            f'Hello {customer_name},\n\n'
            f'Your booking request has been received for {activity_name}.\n\n'
            f'Travel date: {travel_date}\n'
            f'Number of people: {activity_booking.number_of_people}\n'
            f'Payment method: {payment_method}\n'
            f'Total amount: {amount}\n\n'
            'We will contact you if any additional details are needed.\n\n'
            'Thank you,\n'
            'TravelMate Team'
        )
        send_mail(
            customer_subject,
            customer_message,
            from_email,
            [customer_email],
            fail_silently=True,
        )

    if vendor_email:
        vendor_subject = f'New Activity Booking Alert - {activity_name}'
        vendor_message = (
            'Hello,\n\n'
            f'You have received a new booking for activity {activity_name}.\n\n'
            f'Traveler: {customer_name}\n'
            f'Email: {activity_booking.email}\n'
            f'Phone: {activity_booking.phone}\n'
            f'Travel date: {travel_date}\n'
            f'People: {activity_booking.number_of_people}\n'
            f'Payment method: {payment_method}\n'
            f'Total amount: {amount}\n\n'
            'Please check your admin dashboard for full details.\n\n'
            'TravelMate System'
        )
        send_mail(
            vendor_subject,
            vendor_message,
            from_email,
            [vendor_email],
            fail_silently=True,
        )


def _verify_esewa_transaction(reference, payment_token, amount, product_code=''):
    product_code = str(product_code or getattr(settings, 'ESEWA_PRODUCT_CODE', '')).strip()
    status_url = str(getattr(settings, 'ESEWA_STATUS_URL', '')).strip()

    if not product_code:
        return False, 'eSewa product code is not configured in settings.', ''
    if not status_url:
        return False, 'eSewa status URL is not configured in settings.', ''
    if not payment_token:
        return False, 'Missing payment token from callback.', ''
    if amount is None:
        return False, 'Missing payment amount in callback.', ''

    status_query = {
        'product_code': product_code,
        'total_amount': f'{amount:.2f}',
        'transaction_uuid': str(payment_token).strip(),
    }
    separator = '&' if '?' in status_url else '?'
    status_request_url = f"{status_url}{separator}{urlencode(status_query)}"

    try:
        status_request = Request(status_request_url, method='GET')
        with urlopen(status_request, timeout=12) as response:
            response_body = response.read().decode('utf-8', errors='ignore').strip()
        status_payload = json.loads(response_body)
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return False, 'Could not reach eSewa status verification service.', ''

    if not isinstance(status_payload, dict):
        return False, 'Invalid response from eSewa status verification service.', ''

    status_value = str(status_payload.get('status', '')).strip().upper()
    verified_reference = str(
        status_payload.get('ref_id')
        or status_payload.get('transaction_code')
        or reference
        or ''
    ).strip()

    if status_value in {'COMPLETE', 'SUCCESS'}:
        return True, '', verified_reference
    if status_value == 'PENDING':
        return False, 'eSewa payment is still pending. Please try again after a moment.', verified_reference
    if status_value in {'FAILED', 'CANCELED', 'CANCELLED'}:
        return False, f'eSewa status check returned {status_value}.', verified_reference
    return False, 'eSewa payment status could not be confirmed.', verified_reference


def _generate_esewa_v2_signature(total_amount, transaction_uuid, product_code):
    secret_key = str(getattr(settings, 'ESEWA_SECRET_KEY', '')).strip()
    if not secret_key:
        return ''

    message = f'total_amount={total_amount:.2f},transaction_uuid={transaction_uuid},product_code={product_code}'
    digest = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(digest).decode('utf-8')


def _build_esewa_payment_request(request, amount, payment_token):
    payment_url = str(getattr(settings, 'ESEWA_FORM_URL', '')).strip()
    product_code = str(getattr(settings, 'ESEWA_PRODUCT_CODE', '')).strip()

    if not product_code:
        return None, 'eSewa product code is not configured.'
    if not payment_url:
        return None, 'eSewa payment form URL is not configured.'
    if not _is_external_http_url(payment_url):
        return None, 'eSewa form URL must be an absolute external URL.'
    if amount is None or amount <= 0:
        return None, 'Invalid booking total for eSewa payment.'

    success_url = request.build_absolute_uri(reverse('esewa_callback'))
    failure_url = request.build_absolute_uri(reverse('esewa_failure'))

    signature = _generate_esewa_v2_signature(amount, payment_token, product_code)
    if not signature:
        return None, 'eSewa secret key is not configured for v2 form signing.'

    payment_payload = {
        'amount': f'{amount:.2f}',
        'tax_amount': '0',
        'total_amount': f'{amount:.2f}',
        'transaction_uuid': payment_token,
        'product_code': product_code,
        'product_service_charge': '0',
        'product_delivery_charge': '0',
        'success_url': success_url,
        'failure_url': failure_url,
        'signed_field_names': 'total_amount,transaction_uuid,product_code',
        'signature': signature,
    }

    return {
        'payment_url': payment_url,
        'payment_payload': payment_payload,
        'payment_token': payment_token,
        'amount': amount,
    }, ''


def _build_package_esewa_payment_request(request, booking):
    amount = _parse_decimal_amount(booking.total_amount)
    payment_token = f'BOOKING-{booking.pk}'
    return _build_esewa_payment_request(request, amount, payment_token)


def _build_activity_esewa_payment_request(request, activity_booking):
    amount = _parse_decimal_amount(activity_booking.total_amount)
    payment_token = f'ACTIVITY-BOOKING-{activity_booking.pk}'
    return _build_esewa_payment_request(request, amount, payment_token)


def _redirect_after_login(request, user):
    if user.is_staff or user.is_superuser or user.role == CustomUser.Role.ADMIN:
        return redirect('/admin/')
    if user.role == CustomUser.Role.VENDOR:
        from vendor.models import VendorProfile

        profile = VendorProfile.objects.filter(user=user).first()
        if profile and profile.account_status == VendorProfile.AccountStatus.DEACTIVATED:
            logout(request)
            messages.error(request, 'Your vendor account has been deactivated. Please contact support for assistance.')
            return redirect('login')
        if profile and profile.verification_status == VendorProfile.VerificationStatus.APPROVED:
            return redirect('vendor:dashboard')
        if profile and profile.verification_status == VendorProfile.VerificationStatus.REJECTED and profile.rejection_reason:
            messages.error(request, f'Your vendor account was rejected: {profile.rejection_reason}')
            return redirect('home')
        messages.warning(request, 'Your vendor registration is pending approval.')
        return redirect('home')
    return redirect('home')


def _ensure_vendor_profile(user):
    if user.role != CustomUser.Role.VENDOR:
        return
    from vendor.models import VendorProfile

    VendorProfile.objects.get_or_create(
        user=user,
        defaults={
            'company_name': user.get_full_name() or user.username,
        },
    )


def _ensure_platform_admin(user):
    is_platform_admin = user.is_authenticated and (
        user.is_superuser or user.role == CustomUser.Role.ADMIN or (user.is_staff and not user.is_vendor)
    )
    if not is_platform_admin:
        raise PermissionDenied


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()      #  password hashed automatically
            login(request, user)    #  auto login after signup
            return _redirect_after_login(request, user)
    else:
        form = SignUpForm()
    return render(request, "signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return _redirect_after_login(request, request.user)

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            _ensure_vendor_profile(user)
            return _redirect_after_login(request, user)
    else:
        form = LoginForm()
    return render(request, "login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")



def home(request):
    from vendor.models import VendorProfile
    from django.db.models import Count

    # Destinations
    destinations = Destination.objects.all()[:8]

    # Featured packages — approved, active, ordered by rating
    packages = Package.objects.filter(
        is_active=True, approval_status=ApprovalStatus.APPROVED
    ).select_related('vendor').order_by('-rating', '-created_at')[:8]

    # Featured activities — approved, active
    activities = Activity.objects.filter(
        is_active=True, approval_status=ApprovalStatus.APPROVED
    ).select_related('vendor', 'category').prefetch_related('images').order_by('-rating', '-created_at')[:8]

    # Hero stats
    stats = {
        'total_packages': Package.objects.filter(is_active=True, approval_status=ApprovalStatus.APPROVED).count(),
        'total_activities': Activity.objects.filter(is_active=True, approval_status=ApprovalStatus.APPROVED).count(),
        'total_vendors': VendorProfile.objects.filter(verification_status='APPROVED').count(),
    }

    context = {
        "featured_destinations": destinations,
        "featured_packages": packages,
        "featured_activities": activities,
        "stats": stats,
    }
    context.update(_favorite_card_context(request))
    return render(request, "home.html", context)


def destination_list(request):
    # Show all destinations (countries)
    destinations = Destination.objects.all()
    return render(request, 'destination_list.html', {
        'destinations': destinations
    })


def destination_detail(request, pk):
    # Get destination regardless of active status
    destination = get_object_or_404(Destination, pk=pk)
    # Get only active packages for this destination (country)
    packages = Package.objects.filter(
        destination=destination,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
    ).order_by('-created_at')
    
    context = {
        'destination': destination,
        'packages': packages,
    }
    context.update(_favorite_card_context(request))
    return render(request, 'destination_detail.html', context)


# ----------------- Package views -----------------
def package_list(request, category=None, hot_sales=False):
    qs = Package.objects.filter(is_active=True, approval_status=ApprovalStatus.APPROVED).select_related('vendor', 'destination')
    title = 'All Packages'

    if hot_sales:
        qs = qs.none()
        title = 'Packages'

    # Search
    search_q = request.GET.get('q', '').strip()
    if search_q:
        qs = qs.filter(
            Q(title__icontains=search_q)
            | Q(description__icontains=search_q)
            | Q(destination__name__icontains=search_q)
            | Q(city__icontains=search_q)
            | Q(vendor__company_name__icontains=search_q)
        )

    # Filter by category (from dropdown or URL)
    filter_cat = request.GET.get('cat', '').strip()
    active_cat = filter_cat or (category or '')
    if active_cat:
        qs = qs.filter(category=active_cat)
        cat_label = dict(Package.Category.choices).get(active_cat, '')
        if cat_label:
            title = cat_label + ' Packages'

    # Filter by destination
    filter_dest = request.GET.get('dest', '').strip()
    if filter_dest:
        qs = qs.filter(destination__id=filter_dest)

    # Sort
    sort_by = request.GET.get('sort', '').strip()
    if sort_by == 'price_low':
        qs = qs.order_by('price')
    elif sort_by == 'price_high':
        qs = qs.order_by('-price')
    elif sort_by == 'rating':
        qs = qs.order_by('-rating')
    elif sort_by == 'newest':
        qs = qs.order_by('-created_at')
    else:
        qs = qs.order_by('-rating', '-created_at')

    destinations = Destination.objects.all().order_by('name')

    context = {
        'packages': qs,
        'category': category,
        'hot_sales': hot_sales,
        'title': title,
        'search_q': search_q,
        'filter_cat': active_cat,
        'filter_dest': filter_dest,
        'sort_by': sort_by,
        'category_choices': Package.Category.choices,
        'destinations': destinations,
    }
    context.update(_favorite_card_context(request))
    return render(request, 'packages_list.html', context)


def hot_sale_list(request):
    hot_sales = HotSale.objects.filter(
        is_active=True,
    ).filter(
        Q(package__is_active=True, package__approval_status=ApprovalStatus.APPROVED)
        | Q(activity__is_active=True, activity__approval_status=ApprovalStatus.APPROVED),
    ).select_related('package', 'package__destination', 'activity', 'activity__category').prefetch_related('activity__images')

    context = {
        'hot_sales': hot_sales,
        'title': 'Hot Sales',
    }
    context.update(_favorite_card_context(request))
    return render(request, 'hot_sales.html', context)


def activity_detail(request, pk):
    activity = get_object_or_404(
        Activity.objects.select_related('category', 'vendor', 'vendor__user').prefetch_related('images'),
        pk=pk,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
    )
    hot_sale_context = _is_hot_sale_context(request)
    active_hot_sale = None
    if hot_sale_context:
        active_hot_sale = activity.hot_sale_entries.filter(is_active=True).order_by('-updated_at', '-created_at').first()
    activity_primary_image = activity.images.first()
    booking_unit_price = active_hot_sale.sale_price if active_hot_sale else activity.price
    blocked_dates = list(activity.unavailable_dates.filter(date__gte=timezone.localdate()).order_by('date'))
    blocked_dates_iso = [entry.date.isoformat() for entry in blocked_dates]
    activity_reviews = activity.reviews.select_related('user').all()
    can_review_activity = _can_user_review_activity(request.user, activity)

    booking_initial = {'travel_date': timezone.localdate(), 'number_of_people': 1}
    if request.user.is_authenticated:
        booking_initial.update({
            'full_name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
        })

    user_activity_review = None
    if request.user.is_authenticated:
        user_activity_review = activity_reviews.filter(user=request.user).first()

    review_initial = {}
    if user_activity_review:
        review_initial = {
            'rating': user_activity_review.rating,
            'comment': user_activity_review.comment,
        }

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'booking')

        if form_type == 'review':
            if not request.user.is_authenticated:
                return redirect('login')

            if not can_review_activity:
                messages.error(request, 'You can review this activity only after making a booking.')
                return redirect('activity_detail', pk=activity.pk)

            review_form = ActivityReviewForm(request.POST, instance=user_activity_review)
            booking_form = ActivityBookingForm(initial=booking_initial, activity=activity)
            if review_form.is_valid():
                activity_review = review_form.save(commit=False)
                activity_review.activity = activity
                activity_review.user = request.user
                activity_review.save()
                success_message = 'Your activity review was submitted successfully.'
                if user_activity_review:
                    success_message = 'Your activity review was updated successfully.'
                messages.success(request, success_message)
                return redirect('activity_detail', pk=activity.pk)
        else:
            if not request.user.is_authenticated:
                return redirect('login')

            blocked_response = _ensure_customer_booking_access(request)
            if blocked_response:
                return blocked_response

            booking_form = ActivityBookingForm(request.POST, activity=activity)
            review_form = ActivityReviewForm(initial=review_initial, instance=user_activity_review)
            if booking_form.is_valid():
                activity_booking = booking_form.save(commit=False)
                activity_booking.activity = activity
                activity_booking.user = request.user
                if booking_unit_price is not None and activity_booking.number_of_people:
                    activity_booking.total_amount = booking_unit_price * activity_booking.number_of_people
                activity_booking.save()
                _send_new_activity_booking_emails(activity_booking)
                if activity_booking.payment_method == ActivityBooking.PaymentMethod.ESEWA:
                    payment_request, payment_error = _build_activity_esewa_payment_request(request, activity_booking)
                    if payment_error:
                        activity_booking.payment_status = ActivityBooking.PaymentStatus.FAILED
                        activity_booking.save()
                        messages.error(request, f'Could not start eSewa payment: {payment_error}')
                        return redirect('activity_detail', pk=activity.pk)

                    return render(request, 'esewa_redirect.html', {
                        'booking': activity_booking,
                        'item_name': activity.name,
                        'item_type': 'activity',
                        'cancel_url': reverse('activity_detail', kwargs={'pk': activity.pk}),
                        'esewa_payment_url': payment_request['payment_url'],
                        'esewa_payload': payment_request['payment_payload'],
                    })

                messages.success(request, 'Your activity booking request has been submitted successfully.')
                return redirect('activity_detail', pk=activity.pk)
    else:
        booking_form = ActivityBookingForm(initial=booking_initial, activity=activity)
        review_form = ActivityReviewForm(initial=review_initial, instance=user_activity_review)

    return render(request, 'activity_detail.html', {
        'activity': activity,
        'active_hot_sale': active_hot_sale,
        'hot_sale_context': hot_sale_context,
        'activity_primary_image': activity_primary_image,
        'booking_form': booking_form,
        'booking_unit_price': booking_unit_price,
        'blocked_dates': blocked_dates,
        'blocked_dates_iso': blocked_dates_iso,
        'review_form': review_form,
        'activity_reviews': activity_reviews,
        'can_review_activity': can_review_activity,
        'user_activity_review': user_activity_review,
    })


def package_detail(request, slug):
    package = get_object_or_404(
        Package.objects.prefetch_related('itinerary_entries'),
        slug=slug,
        is_active=True,
        approval_status=ApprovalStatus.APPROVED,
    )
    is_favorite = False
    itinerary_days = list(package.itinerary_entries.all())
    blocked_dates = list(package.unavailable_dates.filter(date__gte=timezone.localdate()).order_by('date'))
    blocked_dates_iso = [entry.date.isoformat() for entry in blocked_dates]
    hot_sale_context = _is_hot_sale_context(request)
    active_hot_sale = None
    if hot_sale_context:
        active_hot_sale = package.hot_sale_entries.filter(is_active=True).order_by('-updated_at', '-created_at').first()
    booking_unit_price = active_hot_sale.sale_price if active_hot_sale else package.price
    open_booking_box = request.method == 'GET' and request.GET.get('open_booking') in {'1', 'true', 'yes'}
    package_reviews = package.reviews.select_related('user').all()
    can_review_package = _can_user_review_package(request.user, package)
    is_customer_user = _is_customer_user(request.user) if request.user.is_authenticated else False
    can_book_package = (not request.user.is_authenticated) or _is_customer_user(request.user)
    can_submit_inquiry = (not request.user.is_authenticated) or is_customer_user

    if request.user.is_authenticated:
        is_favorite = request.user.favorite_packages.filter(pk=package.pk).exists()

    user_package_review = None
    if request.user.is_authenticated:
        user_package_review = package_reviews.filter(user=request.user).first()

    review_initial = {}
    if user_package_review:
        review_initial = {
            'rating': user_package_review.rating,
            'comment': user_package_review.comment,
        }

    booking_initial = {'travel_date': timezone.localdate(), 'number_of_people': 1}
    inquiry_initial = {}
    if request.user.is_authenticated:
        booking_initial.update({
            'full_name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
        })
        inquiry_initial = {
            'full_name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
        }

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'booking':
            if not request.user.is_authenticated:
                return redirect('login')

            blocked_response = _ensure_customer_booking_access(request)
            if blocked_response:
                return blocked_response

            booking_form = BookingForm(request.POST, package=package)
            inquiry_form = InquiryForm(initial=inquiry_initial)
            review_form = PackageReviewForm(initial=review_initial, instance=user_package_review)
            if booking_form.is_valid():
                booking = booking_form.save(commit=False)
                booking.package = package
                booking.user = request.user
                if booking_unit_price is not None and booking.number_of_people:
                    booking.total_amount = booking_unit_price * booking.number_of_people
                booking.save()
                _send_new_booking_emails(booking)
                if booking.payment_method == Booking.PaymentMethod.ESEWA:
                    payment_request, payment_error = _build_package_esewa_payment_request(request, booking)
                    if payment_error:
                        booking.payment_status = Booking.PaymentStatus.FAILED
                        booking.save()
                        messages.error(request, f'Could not start eSewa payment: {payment_error}')
                        return redirect('package_detail', slug=slug)

                    return render(request, 'esewa_redirect.html', {
                        'booking': booking,
                        'item_name': package.title,
                        'item_type': 'package',
                        'cancel_url': reverse('package_detail', kwargs={'slug': package.slug}),
                        'esewa_payment_url': payment_request['payment_url'],
                        'esewa_payload': payment_request['payment_payload'],
                    })
                else:
                    messages.success(request, 'Your booking request has been submitted successfully.')
                return redirect('package_detail', slug=slug)
        elif form_type == 'inquiry':
            blocked_response = _ensure_customer_inquiry_access(request)
            if blocked_response:
                return blocked_response

            booking_form = BookingForm(initial=booking_initial, package=package)
            inquiry_form = InquiryForm(request.POST)
            review_form = PackageReviewForm(initial=review_initial, instance=user_package_review)
            if inquiry_form.is_valid():
                inquiry = inquiry_form.save(commit=False)
                inquiry.package = package
                if request.user.is_authenticated:
                    inquiry.user = request.user
                inquiry.save()
                messages.success(request, 'Your inquiry has been sent. Our team will contact you soon.')
                return redirect('package_detail', slug=slug)
        elif form_type == 'review':
            if not request.user.is_authenticated:
                return redirect('login')

            if not can_review_package:
                messages.error(request, 'You can review this package only after making a booking.')
                return redirect('package_detail', slug=slug)

            booking_form = BookingForm(initial=booking_initial, package=package)
            inquiry_form = InquiryForm(initial=inquiry_initial)
            review_form = PackageReviewForm(request.POST, instance=user_package_review)
            if review_form.is_valid():
                package_review = review_form.save(commit=False)
                package_review.package = package
                package_review.user = request.user
                package_review.save()
                success_message = 'Your package review was submitted successfully.'
                if user_package_review:
                    success_message = 'Your package review was updated successfully.'
                messages.success(request, success_message)
                return redirect('package_detail', slug=slug)
        else:
            booking_form = BookingForm(initial=booking_initial, package=package)
            inquiry_form = InquiryForm(initial=inquiry_initial)
            review_form = PackageReviewForm(initial=review_initial, instance=user_package_review)
    else:
        booking_form = BookingForm(initial=booking_initial, package=package)
        inquiry_form = InquiryForm(initial=inquiry_initial)
        review_form = PackageReviewForm(initial=review_initial, instance=user_package_review)

    return render(request, 'package_detail.html', {
        'package': package,
        'hot_sale_context': hot_sale_context,
        'booking_form': booking_form,
        'inquiry_form': inquiry_form,
        'review_form': review_form,
        'is_favorite': is_favorite,
        'itinerary_days': itinerary_days,
        'blocked_dates': blocked_dates,
        'blocked_dates_iso': blocked_dates_iso,
        'active_hot_sale': active_hot_sale,
        'booking_unit_price': booking_unit_price,
        'open_booking_box': open_booking_box,
        'package_reviews': package_reviews,
        'can_review_package': can_review_package,
        'can_book_package': can_book_package,
        'can_submit_inquiry': can_submit_inquiry,
        'is_customer_user': is_customer_user,
        'user_package_review': user_package_review,
    })


@login_required
def profile_view(request):
    if request.user.role == CustomUser.Role.VENDOR:
        return redirect('vendor:dashboard')

    bookings = (
        Booking.objects
        .filter(user=request.user)
        .visible_in_listings()
        .select_related('package', 'package__destination')
        .order_by('-created_at')
    )
    activity_bookings = (
        ActivityBooking.objects
        .filter(user=request.user)
        .visible_in_listings()
        .select_related('activity', 'activity__category')
        .order_by('-created_at')
    )
    inquiries = Inquiry.objects.filter(user=request.user).select_related('package').order_by('-created_at')
    favorite_packages = request.user.favorite_packages.filter(is_active=True).select_related('destination').order_by('-updated_at')
    favorite_activities = request.user.favorite_activities.filter(is_active=True).select_related('category').order_by('-created_at')
    total_favorite_count = favorite_packages.count() + favorite_activities.count()

    return render(request, 'profile.html', {
        'bookings': bookings,
        'activity_bookings': activity_bookings,
        'total_booking_count': bookings.count() + activity_bookings.count(),
        'inquiries': inquiries,
        'favorite_packages': favorite_packages,
        'favorite_activities': favorite_activities,
        'total_favorite_count': total_favorite_count,
    })


@customer_only(error_message='Only customers can add packages to favorites.')
@login_required
def toggle_favorite_package(request, slug):
    if request.method != 'POST':
        return redirect('package_detail', slug=slug)

    package = get_object_or_404(Package, slug=slug, is_active=True, approval_status=ApprovalStatus.APPROVED)
    if request.user.favorite_packages.filter(pk=package.pk).exists():
        request.user.favorite_packages.remove(package)
        messages.info(request, 'Removed from favorites.')
    else:
        request.user.favorite_packages.add(package)
        messages.success(request, 'Added to favorites.')

    if request.POST.get('next') == 'profile':
        return redirect('profile')
    return _safe_next_redirect(request, redirect('package_detail', slug=slug))


@customer_only(error_message='Only customers can add activities to favorites.')
@login_required
def toggle_favorite_activity(request, pk):
    if request.method != 'POST':
        return redirect('activity_detail', pk=pk)

    activity = get_object_or_404(Activity, pk=pk, is_active=True, approval_status=ApprovalStatus.APPROVED)
    if request.user.favorite_activities.filter(pk=activity.pk).exists():
        request.user.favorite_activities.remove(activity)
        messages.info(request, 'Removed from favorites.')
    else:
        request.user.favorite_activities.add(activity)
        messages.success(request, 'Added to favorites.')

    if request.POST.get('next') == 'profile':
        return redirect('profile')
    return _safe_next_redirect(request, redirect('activity_detail', pk=activity.pk))


@csrf_exempt
def esewa_callback(request):
    callback = _read_esewa_callback_payload(request)
    booking_target, booking_id = _extract_booking_target_from_token(callback['booking_token'])
    if booking_id is None:
        messages.error(request, 'Invalid eSewa callback: booking identifier is missing.')
        return redirect('home')

    if booking_target == 'activity':
        booking = ActivityBooking.objects.filter(pk=booking_id).select_related('activity').first()
        if not booking:
            messages.error(request, 'Unable to verify payment: activity booking was not found.')
            return redirect('home')

        if booking.payment_status == ActivityBooking.PaymentStatus.PAID:
            messages.info(request, 'This activity booking is already marked as paid.')
            return redirect('activity_detail', pk=booking.activity.pk)

        callback_amount = _parse_decimal_amount(callback['amount'])
        expected_amount = _parse_decimal_amount(booking.total_amount)

        if callback_amount is None:
            booking.payment_status = ActivityBooking.PaymentStatus.FAILED
            booking.save()
            messages.error(request, 'Payment callback did not include a valid amount.')
            return redirect('activity_detail', pk=booking.activity.pk)

        if expected_amount is None or callback_amount != expected_amount:
            booking.payment_status = ActivityBooking.PaymentStatus.FAILED
            booking.save()
            messages.error(request, 'Payment verification failed because the amount does not match the booking total.')
            return redirect('activity_detail', pk=booking.activity.pk)

        status_text = str(callback.get('status') or '').strip().upper()
        if status_text and status_text in {'FAILED', 'CANCELED', 'CANCELLED', 'ERROR'}:
            booking.payment_status = ActivityBooking.PaymentStatus.FAILED
            if callback['reference']:
                booking.transaction_reference = str(callback['reference']).strip()
            booking.save()
            messages.error(request, 'eSewa marked this payment as failed.')
            return redirect('activity_detail', pk=booking.activity.pk)

        verified, reason, verified_reference = _verify_esewa_transaction(
            reference=callback['reference'],
            payment_token=callback['booking_token'],
            amount=callback_amount,
            product_code=callback['product_code'],
        )

        if not verified:
            booking.payment_status = ActivityBooking.PaymentStatus.FAILED
            if callback['reference'] or verified_reference:
                booking.transaction_reference = str(callback['reference'] or verified_reference).strip()
            booking.save()
            messages.error(request, f'Payment verification failed: {reason}')
            return redirect('activity_detail', pk=booking.activity.pk)

        booking.payment_method = ActivityBooking.PaymentMethod.ESEWA
        booking.payment_status = ActivityBooking.PaymentStatus.PAID
        booking.transaction_reference = str(verified_reference or callback['reference'] or '').strip()
        booking.save()
        messages.success(request, 'Activity payment verified successfully through eSewa.')
        return redirect('activity_detail', pk=booking.activity.pk)

    booking = Booking.objects.filter(pk=booking_id).select_related('package').first()
    if not booking:
        messages.error(request, 'Unable to verify payment: booking was not found.')
        return redirect('home')

    if booking.payment_status == Booking.PaymentStatus.PAID:
        messages.info(request, 'This booking is already marked as paid.')
        return redirect('package_detail', slug=booking.package.slug)

    callback_amount = _parse_decimal_amount(callback['amount'])
    expected_amount = _parse_decimal_amount(booking.total_amount)

    if callback_amount is None:
        booking.payment_status = Booking.PaymentStatus.FAILED
        booking.save()
        messages.error(request, 'Payment callback did not include a valid amount.')
        return redirect('package_detail', slug=booking.package.slug)

    if expected_amount is None or callback_amount != expected_amount:
        booking.payment_status = Booking.PaymentStatus.FAILED
        booking.save()
        messages.error(request, 'Payment verification failed because the amount does not match the booking total.')
        return redirect('package_detail', slug=booking.package.slug)

    status_text = str(callback.get('status') or '').strip().upper()
    if status_text and status_text in {'FAILED', 'CANCELED', 'CANCELLED', 'ERROR'}:
        booking.payment_status = Booking.PaymentStatus.FAILED
        if callback['reference']:
            booking.transaction_reference = str(callback['reference']).strip()
        booking.save()
        messages.error(request, 'eSewa marked this payment as failed.')
        return redirect('package_detail', slug=booking.package.slug)

    verified, reason, verified_reference = _verify_esewa_transaction(
        reference=callback['reference'],
        payment_token=callback['booking_token'],
        amount=callback_amount,
        product_code=callback['product_code'],
    )

    if not verified:
        booking.payment_status = Booking.PaymentStatus.FAILED
        if callback['reference'] or verified_reference:
            booking.transaction_reference = str(callback['reference'] or verified_reference).strip()
        booking.save()
        messages.error(request, f'Payment verification failed: {reason}')
        return redirect('package_detail', slug=booking.package.slug)

    booking.payment_method = Booking.PaymentMethod.ESEWA
    booking.payment_status = Booking.PaymentStatus.PAID
    booking.transaction_reference = str(verified_reference or callback['reference'] or '').strip()
    booking.save()
    messages.success(request, 'Payment verified successfully through eSewa.')
    return redirect('package_detail', slug=booking.package.slug)


@csrf_exempt
def esewa_failure(request):
    callback = _read_esewa_callback_payload(request)
    booking_target, booking_id = _extract_booking_target_from_token(callback['booking_token'])
    if booking_id is None:
        messages.error(request, 'eSewa payment was cancelled.')
        return redirect('home')

    if booking_target == 'activity':
        booking = ActivityBooking.objects.filter(pk=booking_id).select_related('activity').first()
        if not booking:
            messages.error(request, 'eSewa payment was cancelled.')
            return redirect('home')

        if booking.payment_status == ActivityBooking.PaymentStatus.PAID:
            messages.info(request, 'This activity booking is already paid.')
            return redirect('activity_detail', pk=booking.activity.pk)

        booking.payment_status = ActivityBooking.PaymentStatus.FAILED
        if callback['reference']:
            booking.transaction_reference = str(callback['reference']).strip()
        booking.save()
        messages.error(request, 'eSewa payment was cancelled or failed.')
        return redirect('activity_detail', pk=booking.activity.pk)

    booking = Booking.objects.filter(pk=booking_id).select_related('package').first()
    if not booking:
        messages.error(request, 'eSewa payment was cancelled.')
        return redirect('home')

    if booking.payment_status == Booking.PaymentStatus.PAID:
        messages.info(request, 'This booking is already paid.')
        return redirect('package_detail', slug=booking.package.slug)

    booking.payment_status = Booking.PaymentStatus.FAILED
    if callback['reference']:
        booking.transaction_reference = str(callback['reference']).strip()
    booking.save()
    messages.error(request, 'eSewa payment was cancelled or failed.')
    return redirect('package_detail', slug=booking.package.slug)


# ─── Search View ───
def search_view(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    search_type = request.GET.get('type', 'all').strip()

    packages = Package.objects.none()
    activities = Activity.objects.none()

    if query or category:
        if search_type in ('all', 'packages'):
            packages = Package.objects.filter(
                is_active=True, approval_status=ApprovalStatus.APPROVED
            ).select_related('vendor', 'destination')
            if query:
                packages = packages.filter(
                    Q(title__icontains=query)
                    | Q(description__icontains=query)
                    | Q(destination__name__icontains=query)
                    | Q(vendor__company_name__icontains=query)
                )
            if category:
                packages = packages.filter(category=category)
            packages = packages.order_by('-rating', '-created_at')[:24]

        if search_type in ('all', 'activities'):
            activities = Activity.objects.filter(
                is_active=True, approval_status=ApprovalStatus.APPROVED
            ).select_related('vendor', 'category').prefetch_related('images')
            if query:
                activities = activities.filter(
                    Q(name__icontains=query)
                    | Q(description__icontains=query)
                    | Q(category__name__icontains=query)
                    | Q(vendor__company_name__icontains=query)
                )
            activities = activities.order_by('-rating', '-created_at')[:24]

    context = {
        'query': query,
        'category': category,
        'search_type': search_type,
        'packages': packages,
        'activities': activities,
        'total_results': len(packages) + len(activities),
    }
    context.update(_favorite_card_context(request))
    return render(request, 'search_results.html', context)


def search_suggestions(request):
    query = (request.GET.get('q') or '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    raw_limit = request.GET.get('limit', 8)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 8
    limit = max(1, min(limit, 20))

    per_source = max(3, (limit // 2))

    from vendor.models import VendorProfile

    package_titles = list(
        Package.objects.filter(
            is_active=True,
            approval_status=ApprovalStatus.APPROVED,
            title__icontains=query,
        )
        .order_by('-rating', 'title')
        .values_list('title', flat=True)[:per_source]
    )
    activity_names = list(
        Activity.objects.filter(
            is_active=True,
            approval_status=ApprovalStatus.APPROVED,
            name__icontains=query,
        )
        .order_by('-rating', 'name')
        .values_list('name', flat=True)[:per_source]
    )
    destination_names = list(
        Destination.objects.filter(name__icontains=query)
        .order_by('name')
        .values_list('name', flat=True)[:per_source]
    )
    vendor_names = list(
        VendorProfile.objects.filter(
            verification_status=VendorProfile.VerificationStatus.APPROVED,
            account_status=VendorProfile.AccountStatus.ACTIVE,
            company_name__icontains=query,
        )
        .order_by('company_name')
        .values_list('company_name', flat=True)[:per_source]
    )

    sources = [
        ['Package', package_titles],
        ['Activity', activity_names],
        ['Destination', destination_names],
        ['Vendor', vendor_names],
    ]

    results = []
    seen = set()

    while len(results) < limit and any(items for _, items in sources):
        for source in sources:
            source_type, items = source
            if not items or len(results) >= limit:
                continue
            value = (items.pop(0) or '').strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append({
                'value': value,
                'type': source_type,
            })

    return JsonResponse({'results': results})


# ─── Activity List View ───
def activity_list_view(request):
    activities = Activity.objects.filter(
        is_active=True, approval_status=ApprovalStatus.APPROVED
    ).select_related('vendor', 'category').prefetch_related('images')

    selected_category = request.GET.get('category', '').strip()
    selected_difficulty = request.GET.get('difficulty', '').strip()
    search_q = request.GET.get('q', '').strip()
    sort_by = request.GET.get('sort', '').strip()

    # Search
    if search_q:
        activities = activities.filter(
            Q(name__icontains=search_q)
            | Q(description__icontains=search_q)
            | Q(category__name__icontains=search_q)
            | Q(vendor__company_name__icontains=search_q)
        )

    # Filter by category
    if selected_category:
        activities = activities.filter(category__name__iexact=selected_category)

    # Filter by difficulty
    if selected_difficulty:
        activities = activities.filter(difficulty_level=selected_difficulty)

    # Sort
    if sort_by == 'price_low':
        activities = activities.order_by('price')
    elif sort_by == 'price_high':
        activities = activities.order_by('-price')
    elif sort_by == 'rating':
        activities = activities.order_by('-rating')
    elif sort_by == 'newest':
        activities = activities.order_by('-created_at')
    else:
        activities = activities.order_by('-rating', '-created_at')

    categories = ActivityCategory.objects.filter(is_active=True).order_by('name')

    context = {
        'activities': activities,
        'categories': categories,
        'selected_category': selected_category,
        'selected_difficulty': selected_difficulty,
        'difficulty_choices': Activity.DifficultyLevel.choices,
        'search_q': search_q,
        'sort_by': sort_by,
    }
    context.update(_favorite_card_context(request))
    return render(request, 'activity_list.html', context)


# ─── Vendor Showcase View ───
def vendor_showcase(request):
    from vendor.models import VendorProfile
    from django.db.models import Count

    vendors = (
        VendorProfile.objects
        .filter(verification_status='APPROVED', account_status='ACTIVE')
        .annotate(
            package_count=Count('packages', filter=Q(packages__is_active=True, packages__approval_status=ApprovalStatus.APPROVED)),
            activity_count=Count('activities', filter=Q(activities__is_active=True, activities__approval_status=ApprovalStatus.APPROVED)),
        )
        .order_by('-package_count', '-activity_count')
    )

    return render(request, 'vendors.html', {'vendors': vendors})
