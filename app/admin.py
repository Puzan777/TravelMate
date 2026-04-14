from itertools import chain
from operator import attrgetter

from django import forms
from django.contrib import admin, messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Activity, ActivityBooking, ActivityCategory, ActivityImage, ApprovalStatus, Booking, CustomUser, Destination,
    DestinationImage,
    HotSale, Package, PackageImage, PackageItinerary, ActivityReview, PackageReview,
)

# Keep Django's nav sidebar enabled so navigation persists on changelists,
# change forms, and custom admin views.
admin.site.enable_nav_sidebar = True

@admin.register(ActivityCategory)
class ActivityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'admin_actions')
    search_fields = ('name',)
    list_display_links = None
    actions = None

    @admin.display(description='Actions')
    def admin_actions(self, obj):
        edit_url = reverse('admin:app_activitycategory_change', args=[obj.pk])
        delete_url = reverse('admin:app_activitycategory_delete', args=[obj.pk])
        return format_html(
            '<div style="display:flex;gap:4px;">'
            '<a class="button" href="{}" style="padding:4px 8px; font-size:11px;">Edit</a>'
            '<a class="button" href="{}" style="padding:4px 8px; font-size:11px; background:#b91c1c; border-color:#b91c1c; color:#fff;">Delete</a>'
            '</div>',
            edit_url,
            delete_url,
        )



def _current_vendor_profile(user):
    return getattr(user, 'vendor_profile', None)


def _is_platform_admin(user):
    return user.is_active and user.is_staff and not getattr(user, 'is_vendor', False)


class MultiImageFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class DestinationAdminForm(forms.ModelForm):
    class Meta:
        model = Destination
        fields = '__all__'

    class Media:
        js = ('admin/destination_multi_upload.js',)

    def is_multipart(self):
        # Force multipart/form-data since we render a file input manually
        return True


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
    form = DestinationAdminForm
    list_display = ('name', 'best_season', 'created_at', 'admin_actions')
    search_fields = ('name', 'short_description', 'visa_info', 'safety_note')
    readonly_fields = ('current_images_manager',)
    list_display_links = None
    actions = None
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'short_description')}),
        ('Travel Info', {'fields': ('best_season', 'visa_info', 'safety_note')}),
        ('Destination Images', {
            'fields': ('current_images_manager',),
        }),
    )

    @admin.display(description='Actions')
    def admin_actions(self, obj):
        edit_url = reverse('admin:app_destination_change', args=[obj.pk])
        delete_url = reverse('admin:app_destination_delete', args=[obj.pk])
        return format_html(
            '<div style="display:flex;gap:4px;">'
            '<a class="button" href="{}" style="padding:4px 8px; font-size:11px;">Edit</a>'
            '<a class="button" href="{}" style="padding:4px 8px; font-size:11px; background:#b91c1c; border-color:#b91c1c; color:#fff;">Delete</a>'
            '</div>',
            edit_url,
            delete_url,
        )

    @admin.display(description='Current Images')
    def current_images_manager(self, obj):
        html_parts = []

        # --- Existing images ---
        if obj and obj.pk:
            images = obj.images.all().order_by('-is_primary', 'created_at')
            has_gallery_images = images.exists()

            # Show legacy hero_image if it exists and no gallery images
            if not has_gallery_images and obj.hero_image:
                html_parts.append(
                    '<div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px;">'
                    '<div style="width:150px; border:2px solid #f59e0b; border-radius:8px; padding:8px; background:#fff; position:relative;">'
                    '<div style="position:absolute;top:4px;left:4px;background:#f59e0b;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;">LEGACY</div>'
                    f'<img src="{obj.hero_image.url}" alt="Legacy hero image" style="height:90px; width:100%; object-fit:cover; border-radius:6px; border:1px solid #e5e7eb; margin-bottom:8px;">'
                    '<div style="display:flex; align-items:center; gap:6px;">'
                    '<input type="checkbox" name="remove_legacy_hero" value="1">'
                    '<label style="font-size:12px; color:#b91c1c;">Delete</label>'
                    '</div>'
                    '</div>'
                    '</div>'
                    '<p style="font-size:12px; color:#6b7280; margin-bottom:12px;">'
                    '<strong>Note:</strong> This is a legacy image. Click <strong>Save</strong> to automatically migrate it into the new gallery system, or add new images below.</p>'
                )
            elif has_gallery_images:
                cards = []
                for image in images:
                    checked = 'checked' if image.is_primary else ''
                    border_color = '#0ea5e9' if image.is_primary else '#d6dbe1'
                    badge = ''
                    if image.is_primary:
                        badge = '<div style="position:absolute;top:4px;left:4px;background:#0ea5e9;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;">COVER</div>'
                    cards.append(
                        f'<div style="width:150px; border:2px solid {border_color}; border-radius:8px; padding:8px; background:#fff; position:relative;">'
                        f'{badge}'
                        f'<img src="{image.image.url}" alt="Destination image" style="height:90px; width:100%; object-fit:cover; border-radius:6px; border:1px solid #e5e7eb; margin-bottom:8px;">'
                        '<div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">'
                        f'<input type="radio" name="primary_image_id" value="{image.pk}" {checked}>'
                        '<label style="font-size:12px; color:#374151;">Set as cover</label>'
                        '</div>'
                        '<div style="display:flex; align-items:center; gap:6px;">'
                        f'<input type="checkbox" name="remove_image_ids" value="{image.pk}">'
                        '<label style="font-size:12px; color:#b91c1c;">Delete</label>'
                        '</div>'
                        '</div>'
                    )
                html_parts.append('<div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px;">' + ''.join(cards) + '</div>')
            else:
                html_parts.append('<p style="color:#6b7280; margin-bottom:12px;">No images uploaded yet.</p>')
        else:
            html_parts.append('<p style="color:#6b7280; margin-bottom:12px;">Save the destination first, then add images.</p>')

        # --- Add Images button + hidden file input + staged preview ---
        html_parts.append(
            '<div>'
            '<button type="button" id="dest-add-images-btn" style="'
            'display:inline-flex; align-items:center; gap:6px; '
            'padding:8px 16px; border-radius:8px; border:1px solid #0ea5e9; '
            'background:#e0f2fe; color:#0369a1; font-weight:700; font-size:13px; '
            'cursor:pointer; transition:all 0.2s;">'
            '<i class="bi bi-plus-circle" style="font-size:16px;"></i> Add Images'
            '</button>'
            '<input type="file" name="new_images" id="id_new_images" accept="image/*" multiple '
            'style="display:none;">'
            '</div>'
            '<div id="dest-staged-preview" style="display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;"></div>'
        )

        return mark_safe('\n'.join(html_parts))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        dest = form.instance

        # --- Auto-migrate legacy hero_image into DestinationImage ---
        if dest.hero_image and not dest.images.exists():
            DestinationImage.objects.create(
                destination=dest,
                image=dest.hero_image,
                is_primary=True,
            )
            # Clear the legacy field after migration
            Destination.objects.filter(pk=dest.pk).update(hero_image='')

        # Handle removal of legacy hero image
        if request.POST.get('remove_legacy_hero') == '1':
            Destination.objects.filter(pk=dest.pk).update(hero_image='')

        remove_image_ids = request.POST.getlist('remove_image_ids')
        if remove_image_ids:
            dest.images.filter(pk__in=remove_image_ids).delete()

        new_images = request.FILES.getlist('new_images')
        created_images = []
        for image_file in new_images:
            created_images.append(
                DestinationImage.objects.create(
                    destination=dest,
                    image=image_file,
                    is_primary=False,
                )
            )

        preferred_primary_id = None

        # Only change cover if user explicitly selected from existing images
        selected_existing_primary = (request.POST.get('primary_image_id') or '').strip()
        if selected_existing_primary.isdigit():
            selected_existing_primary_id = int(selected_existing_primary)
            if dest.images.filter(pk=selected_existing_primary_id).exists():
                preferred_primary_id = selected_existing_primary_id

        images_qs = dest.images.all().order_by('created_at', 'pk')
        if not images_qs.exists():
            return

        if preferred_primary_id is not None:
            # User explicitly chose a cover — apply it
            images_qs.update(is_primary=False)
            images_qs.filter(pk=preferred_primary_id).update(is_primary=True)
        else:
            # Make sure at least one image is marked as primary
            if not images_qs.filter(is_primary=True).exists():
                images_qs.update(is_primary=False)
                first = images_qs.first()
                if first:
                    first.is_primary = True
                    first.save(update_fields=['is_primary'])

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
    list_display = ('title', 'vendor', 'category', 'price', 'rating', 'approval_status', 'is_active', 'created_at', 'admin_actions')
    list_filter = ('vendor', 'category', 'is_active')
    search_fields = ('title', 'slug', 'destination__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('cover_image_preview', 'created_at', 'updated_at')
    list_editable = ('is_active',)
    list_display_links = None

    actions = None

    @admin.display(description='Actions')
    def admin_actions(self, obj):
        view_url = reverse('admin:app_package_change', args=[obj.pk])
        return format_html(
            '<div style="display:flex;gap:4px;">'
            '<a class="button" href="{}" target="_blank" style="padding:4px 8px; font-size:11px; background:var(--vd-ocean); border-color:var(--vd-ocean);">View details</a>'
            '</div>',
            view_url
        )

    fieldsets = (
        (None, {'fields': ('vendor', 'title', 'slug', 'category', 'cover_image_preview', 'image', 'price', 'rating', 'description', 'destination')}),
        ('Trip info', {'fields': ('duration', 'max_people', 'trip_difficulty', 'tour_type', 'max_elevation')}),
        ('Logistics', {'fields': ('accommodation', 'meal', 'vehicle')}),
        ('Optional', {'fields': ('major_highlights', 'itinerary')}),
        ('Status', {'fields': ('approval_status', 'is_active',)}),
    )

    @admin.display(description='Current Image')
    def cover_image_preview(self, obj):
        if not obj:
            return '-'
        image_url = obj.image.url if obj.image else None
        if not image_url:
            primary_image = obj.package_images.filter(is_primary=True).first()
            if not primary_image:
                primary_image = obj.package_images.first()
            if primary_image and primary_image.image:
                image_url = primary_image.image.url
        if not image_url:
            return '-'
        return format_html(
            '<img src="{}" alt="Package image" style="max-height:140px; max-width:220px; border-radius:8px; border:1px solid #e5e7eb;" />',
            image_url,
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(approval_status__in=[ApprovalStatus.APPROVED, ApprovalStatus.PENDING])
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
    list_display = ('name', 'vendor', 'category', 'price', 'difficulty_level', 'approval_status', 'is_active', 'created_at', 'admin_actions')
    list_filter = ('vendor', 'category', 'difficulty_level', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'vendor__company_name', 'category__name')
    readonly_fields = ('cover_image_preview', 'created_at',)
    list_display_links = None

    actions = None

    @admin.display(description='Actions')
    def admin_actions(self, obj):
        view_url = reverse('admin:app_activity_change', args=[obj.pk])
        return format_html(
            '<div style="display:flex;gap:4px;">'
            '<a class="button" href="{}" target="_blank" style="padding:4px 8px; font-size:11px; background:var(--vd-ocean); border-color:var(--vd-ocean);">View details</a>'
            '</div>',
            view_url
        )

    fieldsets = (
        (None, {'fields': ('vendor', 'category', 'name', 'cover_image_preview', 'description', 'price', 'approval_status', 'is_active')}),
        ('Trip details', {'fields': ('duration', 'difficulty_level', 'max_group_size', 'min_age')}),
        ('Safety', {'fields': ('min_weight', 'max_weight', 'equipment_provided', 'safety_notes')}),
        ('System', {'fields': ('created_at',)}),
    )

    @admin.display(description='Current Image')
    def cover_image_preview(self, obj):
        if not obj:
            return '-'
        primary_image = obj.images.filter(is_primary=True).first()
        if not primary_image:
            primary_image = obj.images.first()
        if not primary_image or not primary_image.image:
            return '-'
        return format_html(
            '<img src="{}" alt="Activity image" style="max-height:140px; max-width:220px; border-radius:8px; border:1px solid #e5e7eb;" />',
            primary_image.image.url,
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(approval_status__in=[ApprovalStatus.APPROVED, ApprovalStatus.PENDING])
        if _is_platform_admin(request.user):
            return qs
        return qs.none()

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


@admin.register(ActivityBooking)
class ActivityBookingAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = (
        'activity_name',
        'vendor_name',
        'full_name',
        'number_of_people',
        'payment_method',
        'payment_status',
        'total_amount',
        'travel_date',
        'created_at',
    )
    list_filter = ('activity__vendor', 'payment_method', 'payment_status', 'travel_date', 'created_at')
    search_fields = (
        'activity__name',
        'activity__vendor__company_name',
        'user__username',
        'full_name',
        'nationality',
        'pickup_location',
        'transaction_reference',
    )
    readonly_fields = ('total_amount', 'paid_at', 'created_at')
    fieldsets = (
        ('Booking', {'fields': ('activity', 'user', 'travel_date', 'number_of_people')}),
        ('Traveler', {'fields': ('full_name', 'email', 'phone', 'nationality', 'emergency_contact', 'pickup_location')}),
        ('Payment', {'fields': ('payment_method', 'transaction_reference', 'payment_status', 'total_amount', 'paid_at')}),
        ('System', {'fields': ('created_at',)}),
    )

    def get_queryset(self, request):
        qs = (
            super().get_queryset(request).visible_in_listings()
            .select_related('activity', 'activity__vendor', 'user')
        )
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(activity__vendor=vendor_profile)
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
        if obj.activity and obj.activity.vendor:
            return obj.activity.vendor.company_name
        return '-'

    @admin.display(description='Activity')
    def activity_name(self, obj):
        if not obj.activity:
            return '-'
        name = obj.activity.name or ''
        if len(name) <= 20:
            return name
        return f"{name[:20]}..."


@admin.register(PackageReview)
class PackageReviewAdmin(admin.ModelAdmin):
    list_display = ('package', 'user', 'rating', 'created_at', 'updated_at')
    list_filter = ('rating', 'created_at', 'updated_at')
    search_fields = ('package__title', 'user__username', 'user__email', 'comment')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ActivityReview)
class ActivityReviewAdmin(admin.ModelAdmin):
    list_display = ('activity', 'user', 'rating', 'created_at', 'updated_at')
    list_filter = ('rating', 'created_at', 'updated_at')
    search_fields = ('activity__name', 'user__username', 'user__email', 'comment')
    readonly_fields = ('created_at', 'updated_at')


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




def _earnings_view(request):
    if not (request.user.is_active and request.user.is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    context = {
        **admin.site.each_context(request),
        'title': 'Earnings & Transactions',
    }
    return TemplateResponse(request, 'admin/earnings.html', context)


def _settings_view(request):
    if not (request.user.is_active and request.user.is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    context = {
        **admin.site.each_context(request),
        'title': 'System Settings',
    }
    return TemplateResponse(request, 'admin/settings.html', context)

# Register custom admin URLs
_original_get_urls = admin.AdminSite.get_urls

def _custom_get_urls(self):
    custom_urls = [
        path('pending-approvals/', self.admin_view(_pending_approvals_view), name='pending_approvals'),
        path('live-products/', self.admin_view(_live_products_view), name='live_products'),
        path('earnings/', self.admin_view(_earnings_view), name='earnings'),
        path('settings/', self.admin_view(_settings_view), name='settings'),
    ]
    return custom_urls + _original_get_urls(self)

admin.AdminSite.get_urls = _custom_get_urls
