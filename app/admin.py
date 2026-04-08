from itertools import chain
from operator import attrgetter

from django.contrib import admin, messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Activity, ActivityCategory, ActivityImage, ApprovalStatus, Booking, CustomUser, Destination,
    HotSale, Inquiry, Package, PackageImage, PackageItinerary,
)

# Hide default Django admin nav sidebar; custom dashboard provides navigation.
admin.site.enable_nav_sidebar = False

@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)



def _current_vendor_profile(user):
    return getattr(user, 'vendor_profile', None)


def _is_platform_admin(user):
    return user.is_active and user.is_staff and not getattr(user, 'is_vendor', False)


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'is_superuser', 'is_active', 'view_details')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    @admin.display(description='Details')
    def view_details(self, obj):
        url = reverse('admin:app_customuser_change', args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">View details</a>', url)


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'best_season', 'created_at')
    search_fields = ('name', 'short_description', 'visa_info', 'safety_note')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'hero_image', 'short_description')}),
        ('Travel Info', {'fields': ('best_season', 'visa_info', 'safety_note')}),
        ('System', {'fields': ('created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        if _is_platform_admin(request.user):
            return super().get_queryset(request)
        return super().get_queryset(request).none()

    def has_add_permission(self, request):
        return _is_platform_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return _is_platform_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return _is_platform_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return _is_platform_admin(request.user)


class PackageImageInline(admin.TabularInline):
    model = PackageImage
    extra = 0
    fields = ('image_preview', 'image', 'is_primary')
    readonly_fields = ('image_preview', 'image', 'is_primary')
    can_delete = False

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 100px; max-width: 150px; border-radius: 4px;" />', obj.image.url)
        return "-"

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    inlines = [PackageImageInline]
    list_per_page = 20
    list_display = ('title', 'vendor', 'category', 'price', 'rating', 'approval_status', 'is_active', 'created_at')
    list_filter = ('vendor', 'category', 'approval_status', 'is_active')
    search_fields = ('title', 'slug', 'destination__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active',)

    fieldsets = (
        (None, {'fields': ('vendor', 'title', 'slug', 'category', 'image', 'price', 'rating', 'description', 'destination')}),
        ('Trip info', {'fields': ('duration', 'max_people', 'trip_difficulty', 'activity', 'max_elevation')}),
        ('Logistics', {'fields': ('accommodation', 'meal', 'vehicle')}),
        ('Optional', {'fields': ('major_highlights', 'itinerary')}),
        ('Status', {'fields': ('approval_status', 'is_active',)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(vendor=vendor_profile)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'destination':
            kwargs['queryset'] = Destination.objects.order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            vendor_profile = _current_vendor_profile(request.user)
            if vendor_profile and obj.vendor_id is None:
                obj.vendor = vendor_profile
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff


class ActivityImageInline(admin.TabularInline):
    model = ActivityImage
    extra = 0
    fields = ('image_preview', 'image', 'is_primary')
    readonly_fields = ('image_preview', 'image', 'is_primary')
    can_delete = False

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 100px; max-width: 150px; border-radius: 4px;" />', obj.image.url)
        return "-"

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    inlines = [ActivityImageInline]
    list_per_page = 20
    list_display = ('name', 'vendor', 'category', 'price', 'difficulty_level', 'approval_status', 'is_active', 'created_at')
    list_filter = ('vendor', 'category', 'difficulty_level', 'approval_status', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'vendor__company_name', 'category__name')
    readonly_fields = ('created_at',)

    fieldsets = (
        (None, {'fields': ('vendor', 'category', 'name', 'description', 'price', 'approval_status', 'is_active')}),
        ('Trip details', {'fields': ('duration', 'difficulty_level', 'max_group_size', 'min_age')}),
        ('Safety', {'fields': ('min_weight', 'max_weight', 'equipment_provided', 'safety_notes')}),
        ('System', {'fields': ('created_at',)}),
    )

    def get_queryset(self, request):
        if _is_platform_admin(request.user):
            return super().get_queryset(request)
        return super().get_queryset(request).none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return _is_platform_admin(request.user) and obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return _is_platform_admin(request.user)


@admin.register(HotSale)
class HotSaleAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = ('target_type', 'target_name', 'original_price', 'sale_price', 'savings', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('package__title', 'package__slug', 'activity__name', 'note')
    autocomplete_fields = ('package',)
    readonly_fields = ('original_price', 'created_at', 'updated_at')
    fieldsets = (
        ('Hot Sale', {'fields': ('package', 'activity', 'original_price', 'sale_price', 'note', 'is_active')}),
        ('System', {'fields': ('created_at', 'updated_at')}),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'package':
            package_qs = Package.objects.filter(is_active=True)
            if not request.user.is_superuser:
                vendor_profile = _current_vendor_profile(request.user)
                if vendor_profile:
                    package_qs = package_qs.filter(vendor=vendor_profile)
                else:
                    package_qs = package_qs.none()
            kwargs['queryset'] = package_qs.order_by('title')
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'package':
            formfield.label = 'Search Package'
            formfield.help_text = 'Search and select an existing active package for this hot sale.'
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
            formfield.widget.can_delete_related = False
            formfield.widget.can_view_related = False
        if db_field.name == 'activity':
            activity_qs = Activity.objects.filter(is_active=True)
            if not request.user.is_superuser:
                vendor_profile = _current_vendor_profile(request.user)
                if vendor_profile:
                    activity_qs = activity_qs.filter(vendor=vendor_profile)
                else:
                    activity_qs = activity_qs.none()
            kwargs['queryset'] = activity_qs.order_by('name')
            formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
            formfield.label = 'Search Activity'
            formfield.help_text = 'Search and select an existing active activity for this hot sale.'
            formfield.widget.can_add_related = False
            formfield.widget.can_change_related = False
            formfield.widget.can_delete_related = False
            formfield.widget.can_view_related = False
        return formfield

    @admin.display(description='Type')
    def target_type(self, obj):
        return obj.target_type

    @admin.display(description='Offer')
    def target_name(self, obj):
        return obj.target_name

    @admin.display(description='Original Price')
    def original_price(self, obj):
        if not obj:
            return 'Select a package or activity to preview the original price.'
        return obj.original_price

    @admin.display(description='Savings')
    def savings(self, obj):
        return obj.savings_amount

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(Q(package__vendor=vendor_profile) | Q(activity__vendor=vendor_profile))
        return qs.none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff


@admin.register(PackageItinerary)
class PackageItineraryAdmin(admin.ModelAdmin):
    list_display = ('package', 'day_number', 'title')
    list_filter = ('package__vendor',)
    search_fields = ('package__title', 'title', 'description', 'activities')

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('package', 'package__vendor')
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(package__vendor=vendor_profile)
        return qs.none()


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = (
        'package_short_title',
        'vendor_name',
        'full_name',
        'number_of_people',
        'payment_method',
        'payment_status',
        'total_price',
        'travel_date',
        'created_at',
    )
    list_filter = ('package__vendor', 'payment_method', 'payment_status', 'travel_date', 'created_at')
    search_fields = (
        'package__title',
        'package__vendor__company_name',
        'user__username',
        'full_name',
        'nationality',
        'pickup_location',
        'transaction_reference',
    )
    readonly_fields = ('total_amount', 'paid_at', 'created_at')
    fieldsets = (
        ('Booking', {'fields': ('package', 'user', 'travel_date', 'number_of_people')}),
        ('Traveler', {'fields': ('full_name', 'email', 'phone', 'nationality', 'emergency_contact', 'pickup_location')}),
        ('Payment', {'fields': ('payment_method', 'transaction_reference', 'payment_status', 'total_amount', 'paid_at')}),
        ('System', {'fields': ('created_at',)}),
    )

    def get_queryset(self, request):
        qs = (
            super().get_queryset(request).visible_in_listings()
            .select_related('package', 'package__vendor', 'user')
        )
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(package__vendor=vendor_profile)
        return qs.none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    @admin.display(description='Vendor')
    def vendor_name(self, obj):
        if obj.package and obj.package.vendor:
            return obj.package.vendor.company_name
        return '-'

    @admin.display(description='Package')
    def package_short_title(self, obj):
        if not obj.package:
            return '-'
        title = obj.package.title or ''
        if len(title) <= 17:
            return title
        return f"{title[:17]}..."

    @admin.display(description='Total Price')
    def total_price(self, obj):
        if obj.total_amount is not None:
            return obj.total_amount
        if not obj.package or obj.package.price is None:
            return '-'
        return obj.package.price * obj.number_of_people


class InquiryReplyStatusFilter(admin.SimpleListFilter):
    title = 'reply status'
    parameter_name = 'reply_status'

    def lookups(self, request, model_admin):
        return (
            ('replied', 'Replied'),
            ('unreplied', 'Unreplied'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'replied':
            return queryset.filter(replied_at__isnull=False)
        if self.value() == 'unreplied':
            return queryset.filter(replied_at__isnull=True)
        return queryset


class InquiryAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = ('package', 'full_name', 'email', 'phone', 'inquiry_message', 'reply_status', 'user', 'created_at', 'replied_at')
    list_filter = (InquiryReplyStatusFilter, 'created_at', 'replied_at')
    search_fields = ('package__title', 'full_name', 'email', 'phone', 'message')
    readonly_fields = (
        'package', 'user', 'full_name', 'email', 'phone', 'message',
        'created_at', 'replied_at',
    )
    fieldsets = (
        ('Inquiry', {'fields': ('package', 'user', 'full_name', 'email', 'phone', 'message')}),
        ('Reply', {'fields': ('admin_reply', 'replied_at')}),
        ('System', {'fields': ('created_at',)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(package__vendor=vendor_profile)
        return qs.none()

    def has_add_permission(self, request):
        return False

    @admin.display(description='Inquiry Message')
    def inquiry_message(self, obj):
        if len(obj.message) > 80:
            return f"{obj.message[:80]}..."
        return obj.message

    @admin.display(description='Reply Status')
    def reply_status(self, obj):
        return 'Replied' if obj.admin_reply else 'Pending'


# ────────────────────────────────────────────────────────────────────
# Custom admin views: Pending Approvals & Live Products
# ────────────────────────────────────────────────────────────────────

def _pending_approvals_view(request):
    if not (request.user.is_active and request.user.is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    def _redirect_target():
        next_url = request.POST.get('next')
        if next_url and next_url.startswith('/admin/pending-approvals/') and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url
        return 'admin:pending_approvals'

    if request.method == 'POST':
        item_type = request.POST.get('item_type')
        item_id = request.POST.get('item_id')
        action = request.POST.get('action')
        if item_type and item_id and action in ('approve', 'reject'):
            if action == 'reject':
                rejection_reason = request.POST.get('rejection_reason', '').strip()
                if not rejection_reason:
                    messages.error(request, 'Please provide a reason for rejection.')
                    return redirect(_redirect_target())
            else:
                rejection_reason = None
            
            new_status = ApprovalStatus.APPROVED if action == 'approve' else ApprovalStatus.REJECTED
            
            if item_type == 'package':
                Package.objects.filter(pk=item_id).update(approval_status=new_status, rejection_reason=rejection_reason)
            elif item_type == 'activity':
                Activity.objects.filter(pk=item_id).update(approval_status=new_status, rejection_reason=rejection_reason)
            
            if action == 'approve':
                messages.success(request, 'Item approved successfully.')
            else:
                messages.warning(request, 'Item rejected.')
        return redirect(_redirect_target())

    selected_vendor = request.GET.get('vendor', 'all')
    selected_type = request.GET.get('type', 'all')

    pending_packages = Package.objects.filter(
        approval_status=ApprovalStatus.PENDING,
    ).select_related('vendor').order_by('-created_at')
    pending_activities = Activity.objects.filter(
        approval_status=ApprovalStatus.PENDING,
    ).select_related('vendor').order_by('-created_at')

    vendor_options_map = {}
    for vendor_id, company_name in pending_packages.values_list('vendor_id', 'vendor__company_name'):
        if vendor_id:
            vendor_options_map[vendor_id] = company_name or f'Vendor {vendor_id}'
    for vendor_id, company_name in pending_activities.values_list('vendor_id', 'vendor__company_name'):
        if vendor_id:
            vendor_options_map[vendor_id] = company_name or f'Vendor {vendor_id}'

    vendor_options = [
        {'id': str(vendor_id), 'name': name}
        for vendor_id, name in sorted(vendor_options_map.items(), key=lambda item: (item[1] or '').lower())
    ]

    if selected_vendor != 'all' and selected_vendor.isdigit():
        selected_vendor_id = int(selected_vendor)
        pending_packages = pending_packages.filter(vendor_id=selected_vendor_id)
        pending_activities = pending_activities.filter(vendor_id=selected_vendor_id)

    items = []
    if selected_type in ('all', 'package'):
        for p in pending_packages:
            items.append({
                'name': p.title,
                'item_type': 'package',
                'type_label': 'Package',
                'vendor': p.vendor.company_name if p.vendor else '-',
                'submitted': p.created_at,
                'status': p.approval_status,
                'pk': p.pk,
                'admin_url': reverse('admin:app_package_change', args=[p.pk]),
            })

    if selected_type in ('all', 'activity'):
        for a in pending_activities:
            items.append({
                'name': a.name,
                'item_type': 'activity',
                'type_label': 'Activity',
                'vendor': a.vendor.company_name if a.vendor else '-',
                'submitted': a.created_at,
                'status': a.approval_status,
                'pk': a.pk,
                'admin_url': reverse('admin:app_activity_change', args=[a.pk]),
            })

    items.sort(key=lambda x: x['submitted'], reverse=True)

    paginator = Paginator(items, 12)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)

    context = {
        **admin.site.each_context(request),
        'title': 'Pending Approvals',
        'page_obj': page_obj,
        'vendor_options': vendor_options,
        'selected_vendor': selected_vendor,
        'selected_type': selected_type,
        'query_string': query_params.urlencode(),
        'opts': Package._meta,
    }
    return TemplateResponse(request, 'admin/pending_approvals.html', context)


def _live_products_view(request):
    if not (request.user.is_active and request.user.is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    selected_vendor = request.GET.get('vendor', 'all')
    selected_type = request.GET.get('type', 'all')
    sort_by = request.GET.get('sort', 'newest')

    live_packages = Package.objects.filter(
        approval_status=ApprovalStatus.APPROVED, is_active=True,
    ).select_related('vendor', 'destination').order_by('-updated_at')
    live_activities = Activity.objects.filter(
        approval_status=ApprovalStatus.APPROVED, is_active=True,
    ).select_related('vendor', 'category').order_by('-created_at')

    vendor_options_map = {}
    for vendor_id, company_name in live_packages.values_list('vendor_id', 'vendor__company_name'):
        if vendor_id:
            vendor_options_map[vendor_id] = company_name or f'Vendor {vendor_id}'
    for vendor_id, company_name in live_activities.values_list('vendor_id', 'vendor__company_name'):
        if vendor_id:
            vendor_options_map[vendor_id] = company_name or f'Vendor {vendor_id}'

    vendor_options = [
        {'id': str(vendor_id), 'name': name}
        for vendor_id, name in sorted(vendor_options_map.items(), key=lambda item: (item[1] or '').lower())
    ]

    if selected_vendor != 'all' and selected_vendor.isdigit():
        selected_vendor_id = int(selected_vendor)
        live_packages = live_packages.filter(vendor_id=selected_vendor_id)
        live_activities = live_activities.filter(vendor_id=selected_vendor_id)

    items = []
    if selected_type in ('all', 'package'):
        for p in live_packages:
            items.append({
                'name': p.title,
                'type_label': 'Package',
                'vendor': p.vendor.company_name if p.vendor else '-',
                'category': p.get_category_display() if p.category else '-',
                'price': p.price,
                'created': p.created_at,
                'admin_url': reverse('admin:app_package_change', args=[p.pk]),
            })

    if selected_type in ('all', 'activity'):
        for a in live_activities:
            items.append({
                'name': a.name,
                'type_label': 'Activity',
                'vendor': a.vendor.company_name if a.vendor else '-',
                'category': a.category.name if a.category else '-',
                'price': a.price,
                'created': a.created_at,
                'admin_url': reverse('admin:app_activity_change', args=[a.pk]),
            })

    if sort_by == 'oldest':
        items.sort(key=lambda x: x['created'])
    elif sort_by == 'price_low':
        items.sort(key=lambda x: (x['price'] is None, x['price'] if x['price'] is not None else 0))
    elif sort_by == 'price_high':
        items.sort(key=lambda x: (x['price'] is None, -(x['price'] if x['price'] is not None else 0)))
    elif sort_by == 'name':
        items.sort(key=lambda x: x['name'].lower())
    else:
        sort_by = 'newest'
        items.sort(key=lambda x: x['created'], reverse=True)

    paginator = Paginator(items, 12)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)

    context = {
        **admin.site.each_context(request),
        'title': 'Live Products',
        'page_obj': page_obj,
        'vendor_options': vendor_options,
        'selected_vendor': selected_vendor,
        'selected_type': selected_type,
        'sort_by': sort_by,
        'query_string': query_params.urlencode(),
        'opts': Package._meta,
    }
    return TemplateResponse(request, 'admin/live_products.html', context)


# Register custom admin URLs
_original_get_urls = admin.AdminSite.get_urls

def _custom_get_urls(self):
    custom_urls = [
        path('pending-approvals/', self.admin_view(_pending_approvals_view), name='pending_approvals'),
        path('live-products/', self.admin_view(_live_products_view), name='live_products'),
    ]
    return custom_urls + _original_get_urls(self)

admin.AdminSite.get_urls = _custom_get_urls
