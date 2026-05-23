from itertools import chain
from operator import attrgetter

from django import forms
from django.contrib import admin, messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.http import url_has_allowed_host_and_scheme

import csv
from django.http import HttpResponse

def export_as_csv(modeladmin, request, queryset):
    opts = modeladmin.model._meta
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={opts.verbose_name_plural}.csv'
    writer = csv.writer(response)
    
    # Use only concrete fields to avoid reverse relations raising exceptions
    fields = [field.name for field in opts.concrete_fields]
    writer.writerow(fields)
    for obj in queryset:
        row = []
        for field in fields:
            val = getattr(obj, field, '')
            if callable(val):
                val = val()
            row.append(str(val))
        writer.writerow(row)
    return response

_original_changelist_view = admin.ModelAdmin.changelist_view

def _custom_changelist_view(self, request, extra_context=None):
    if request.GET.get('export', '').lower() == 'csv':
        # Remove 'export' parameter so Django doesn't treat it as an invalid model filter
        request.GET = request.GET.copy()
        request.GET.pop('export', None)
        try:
            cl = self.get_changelist_instance(request)
            queryset = cl.get_queryset(request)
            return export_as_csv(self, request, queryset)
        except Exception:
            pass
    return _original_changelist_view(self, request, extra_context)

admin.ModelAdmin.changelist_view = _custom_changelist_view

from .models import (
    Activity, ActivityBooking, ActivityCategory, ActivityImage, ApprovalStatus, Booking, CustomUser, Destination,
    DestinationImage,
    HotSale, Package, PackageImage, PackageItinerary, ActivityReview, PackageReview, Settlement,
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
    change_form_template = 'admin/app/customuser/change_form.html'

    list_display = ('user_identity', 'email', 'joined_on', 'last_login_on', 'activity_summary', 'view_details')
    list_display_links = None
    list_filter = ()
    search_fields = ('username', 'email')
    ordering = ('-date_joined',)
    list_per_page = 10
    readonly_fields = ('user_identity_detail', 'email', 'joined_on', 'last_login_on', 'activity_detail_metrics')
    fieldsets = (
        ('Customer Account', {
            'fields': ('user_identity_detail', 'email', 'joined_on', 'last_login_on'),
        }),
        ('Engagement', {
            'fields': ('activity_detail_metrics',),
        }),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(
                role=CustomUser.Role.CUSTOMER,
                is_staff=False,
                is_superuser=False,
            )
            .annotate(
                package_booking_count=Count('bookings', distinct=True),
                activity_booking_count=Count('activity_bookings', distinct=True),
                favorite_package_count=Count('favorite_packages', distinct=True),
                favorite_activity_count=Count('favorite_activities', distinct=True),
            )
        )

    @admin.display(description='User')
    def user_identity(self, obj):
        display_name = obj.get_full_name() or obj.username
        return format_html(
            '<div style="display:flex; flex-direction:column; line-height:1.2;">'
            '<strong style="font-size:13px;">{}</strong>'
            '<span style="font-size:11px; color:#64748b;">@{}</span>'
            '</div>',
            display_name,
            obj.username,
        )

    @admin.display(description='Joined')
    def joined_on(self, obj):
        if not obj.date_joined:
            return '-'
        return timezone.localtime(obj.date_joined).strftime('%Y-%m-%d')

    @admin.display(description='Last login')
    def last_login_on(self, obj):
        if not obj.last_login:
            return '-'
        return timezone.localtime(obj.last_login).strftime('%Y-%m-%d %H:%M')

    @admin.display(description='Activity')
    def activity_summary(self, obj):
        total_bookings = getattr(obj, 'package_booking_count', 0) + getattr(obj, 'activity_booking_count', 0)
        total_favorites = getattr(obj, 'favorite_package_count', 0) + getattr(obj, 'favorite_activity_count', 0)
        return format_html(
            '<span style="font-size:12px; color:#334155;">'
            'Bookings: <strong>{}</strong> | Favorites: <strong>{}</strong>'
            '</span>',
            total_bookings,
            total_favorites,
        )

    @admin.display(description='User')
    def user_identity_detail(self, obj):
        display_name = obj.get_full_name() or obj.username
        return format_html(
            '<div style="display:flex; flex-direction:column; gap:2px; line-height:1.25;">'
            '<strong style="font-size:14px; color:#0f172a;">{}</strong>'
            '<span style="font-size:12px; color:#64748b;">@{}</span>'
            '</div>',
            display_name,
            obj.username,
        )

    @admin.display(description='Engagement summary')
    def activity_detail_metrics(self, obj):
        package_booking_count = getattr(obj, 'package_booking_count', obj.bookings.count())
        activity_booking_count = getattr(obj, 'activity_booking_count', obj.activity_bookings.count())
        favorite_package_count = getattr(obj, 'favorite_package_count', obj.favorite_packages.count())
        favorite_activity_count = getattr(obj, 'favorite_activity_count', obj.favorite_activities.count())
        total_bookings = package_booking_count + activity_booking_count
        total_favorites = favorite_package_count + favorite_activity_count
        return format_html(
            '<div style="display:grid; gap:8px; font-size:12px; color:#334155;">'
            '<div><strong>Total bookings:</strong> {}</div>'
            '<div><strong>Total favorites:</strong> {}</div>'
            '<div>Package bookings: {} | Activity bookings: {}</div>'
            '<div>Favorite packages: {} | Favorite activities: {}</div>'
            '</div>',
            total_bookings,
            total_favorites,
            package_booking_count,
            activity_booking_count,
            favorite_package_count,
            favorite_activity_count,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return _is_platform_admin(request.user)

    @admin.display(description='Details')
    def view_details(self, obj):
        url = reverse('admin:app_customuser_change', args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">View details</a>', url)


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    form = DestinationAdminForm
    list_display = ('name', 'best_season', 'is_featured', 'created_at', 'admin_actions')
    search_fields = ('name', 'short_description', 'visa_info', 'safety_note')
    list_editable = ('is_featured',)
    readonly_fields = ('current_images_manager',)
    list_display_links = None
    actions = None
    
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'short_description', 'is_featured')}),
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
    list_display = ('title', 'vendor', 'category', 'price', 'rating', 'is_featured', 'approval_status', 'is_active', 'created_at', 'admin_actions')
    list_filter = ('vendor', 'category', 'is_active', 'is_featured')
    search_fields = ('title', 'slug', 'destination__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('cover_image_preview', 'created_at', 'updated_at')
    list_editable = ('is_featured',)
    list_display_links = None

    actions = None

    @admin.display(description='Actions')
    def admin_actions(self, obj):
        view_url = reverse('admin:app_package_change', args=[obj.pk])
        return format_html(
            '<div style="display:flex;gap:4px;">'
            '<a class="button" href="{}" style="padding:4px 8px; font-size:11px; background:var(--vd-ocean); border-color:var(--vd-ocean);">View details</a>'
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
        qs = super().get_queryset(request)
        # On the list view, show only APPROVED. On the detail view, allow PENDING so the Pending Approvals page still works.
        if getattr(request, 'resolver_match', None) and request.resolver_match.url_name == 'app_package_changelist':
            qs = qs.filter(approval_status=ApprovalStatus.APPROVED)
        else:
            qs = qs.filter(approval_status__in=[ApprovalStatus.APPROVED, ApprovalStatus.PENDING])
        if _is_platform_admin(request.user):
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
        return _is_platform_admin(request.user) and obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)


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
    list_display = ('name', 'vendor', 'category', 'price', 'difficulty_level', 'is_featured', 'approval_status', 'is_active', 'created_at', 'admin_actions')
    list_filter = ('vendor', 'category', 'difficulty_level', 'is_active', 'is_featured', 'created_at')
    search_fields = ('name', 'description', 'vendor__company_name', 'category__name')
    readonly_fields = ('cover_image_preview', 'created_at',)
    list_display_links = None
    list_editable = ('is_featured',)

    actions = None

    @admin.display(description='Actions')
    def admin_actions(self, obj):
        view_url = reverse('admin:app_activity_change', args=[obj.pk])
        return format_html(
            '<div style="display:flex;gap:4px;">'
            '<a class="button" href="{}" style="padding:4px 8px; font-size:11px; background:var(--vd-ocean); border-color:var(--vd-ocean);">View details</a>'
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
        qs = super().get_queryset(request)
        if getattr(request, 'resolver_match', None) and request.resolver_match.url_name == 'app_activity_changelist':
            qs = qs.filter(approval_status=ApprovalStatus.APPROVED)
        else:
            qs = qs.filter(approval_status__in=[ApprovalStatus.APPROVED, ApprovalStatus.PENDING])
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
    list_per_page = 10
    list_display = (
        'package_short_title',
        'vendor_name_short',
        'full_name',
        'payment_method',
        'payment_status',
        'total_price',
        'created_at',
        'view_details',
    )
    list_display_links = None
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

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path(
                '<int:object_id>/detail/',
                self.admin_site.admin_view(self.detail_view),
                name='%s_%s_detail' % info,
            ),
        ]
        return custom_urls + urls

    def detail_view(self, request, object_id):
        if not self.has_view_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        obj = self.get_object(request, object_id)
        if obj is None:
            from django.http import Http404

            raise Http404('Booking not found.')

        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            title='Booking details',
            booking=obj,
            back_url=reverse('admin:app_booking_changelist'),
        )
        return TemplateResponse(request, 'admin/app/booking/detail.html', context)

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
    def vendor_name_short(self, obj):
        if obj.package and obj.package.vendor:
            company_name = obj.package.vendor.company_name or ''
            words = company_name.split()
            if len(words) <= 15:
                return company_name
            return f"{' '.join(words[:15])}..."
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

    @admin.display(description='Action')
    def view_details(self, obj):
        url = reverse('admin:app_booking_detail', args=[obj.pk])
        return format_html('<a class="button" href="{}">View detail</a>', url)


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
        'title': 'Pending Tours',
        'page_obj': page_obj,
        'vendor_options': vendor_options,
        'selected_vendor': selected_vendor,
        'selected_type': selected_type,
        'query_string': query_params.urlencode(),
        'opts': Package._meta,
    }
    return TemplateResponse(request, 'admin/pending_approvals.html', context)


def _earnings_view(request):
    if not (request.user.is_active and request.user.is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    from django.db.models import Sum
    from django.template.response import TemplateResponse
    from django.utils import timezone
    import csv
    from django.http import HttpResponse
    from django.shortcuts import redirect
    from .models import Settlement
    from vendor.models import VendorProfile
    from django.db.models import Q

    if request.method == 'POST' and 'bulk_settle' in request.POST:
        settle_ids = request.POST.getlist('settlement_ids')
        if settle_ids:
            Settlement.objects.filter(id__in=settle_ids, status=Settlement.Status.PENDING).update(
                status=Settlement.Status.SETTLED,
                settled_at=timezone.now()
            )
        return redirect(request.get_full_path())

    qs = Settlement.objects.all().select_related('booking__package__vendor', 'activity_booking__activity__vendor')

    # Custom date filtering
    date_filter = request.GET.get('date_filter', 'all')
    if date_filter != 'all':
        from datetime import timedelta
        now = timezone.now()
        if date_filter == 'this_week':
            start_date = now - timedelta(days=now.weekday())
        elif date_filter == 'this_month':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif date_filter == 'last_3_months':
            start_date = now - timedelta(days=90)
        elif date_filter == 'last_6_months':
            start_date = now - timedelta(days=180)
        elif date_filter == 'this_year':
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = None

    # Base querysets
    vendor_payouts = qs.filter(settlement_direction=Settlement.Direction.PLATFORM_TO_VENDOR, status=Settlement.Status.PENDING)
    commission_collections = qs.filter(settlement_direction=Settlement.Direction.VENDOR_TO_PLATFORM, status=Settlement.Status.PENDING)
    settled_history = qs.filter(status=Settlement.Status.SETTLED)

    # Apply date filters
    if date_filter != 'all' and 'start_date' in locals() and start_date:
        vendor_payouts = vendor_payouts.filter(created_at__gte=start_date)
        commission_collections = commission_collections.filter(created_at__gte=start_date)
        settled_history = settled_history.filter(settled_at__gte=start_date)

    # Apply vendor filtering
    vendor_filter = request.GET.get('vendor_filter', 'all')
    if vendor_filter != 'all' and vendor_filter.isdigit():
        vendor_id = int(vendor_filter)
        vendor_q = Q(booking__package__vendor_id=vendor_id) | Q(activity_booking__activity__vendor_id=vendor_id)
        vendor_payouts = vendor_payouts.filter(vendor_q)
        commission_collections = commission_collections.filter(vendor_q)
        settled_history = settled_history.filter(vendor_q)

    vendor_payouts = vendor_payouts.order_by('-created_at')
    commission_collections = commission_collections.order_by('-created_at')
    settled_history = settled_history.order_by('-settled_at')

    export_tab = request.GET.get('export_tab')
    if export_tab in ['payouts', 'collections', 'history']:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=settlements_{export_tab}.csv'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Vendor', 'Type', 'Method', 'Gross', 'Commission', 'Vendor Net', 'Holder', 'Direction', 'Status', 'Settled At'])
        
        export_qs = vendor_payouts if export_tab == 'payouts' else commission_collections if export_tab == 'collections' else settled_history
        for obj in export_qs:
            vendor = obj.vendor_profile.company_name if obj.vendor_profile else 'Unknown'
            b_type = 'Package' if obj.booking_id else 'Activity'
            method = getattr(obj.booking or obj.activity_booking, 'payment_method', '')
            writer.writerow([
                obj.id, vendor, b_type, method,
                obj.gross_amount, obj.commission_amount, obj.vendor_amount,
                obj.get_money_holder_display(), obj.get_settlement_direction_display(),
                obj.get_status_display(), obj.settled_at
            ])
        return response

    total_pending_payouts = vendor_payouts.aggregate(t=Sum('vendor_amount'))['t'] or 0
    total_pending_collections = commission_collections.aggregate(t=Sum('commission_amount'))['t'] or 0
    
    current_month = timezone.now().month
    current_year = timezone.now().year
    total_settled_this_month = settled_history.filter(settled_at__month=current_month, settled_at__year=current_year).aggregate(t=Sum('gross_amount'))['t'] or 0

    # Calculate Tab Totals based on current filters
    tab_payouts_gross = vendor_payouts.aggregate(t=Sum('gross_amount'))['t'] or 0
    tab_payouts_commission = vendor_payouts.aggregate(t=Sum('commission_amount'))['t'] or 0
    tab_payouts_vendor = vendor_payouts.aggregate(t=Sum('vendor_amount'))['t'] or 0

    tab_collections_gross = commission_collections.aggregate(t=Sum('gross_amount'))['t'] or 0
    tab_collections_commission = commission_collections.aggregate(t=Sum('commission_amount'))['t'] or 0
    tab_collections_vendor = commission_collections.aggregate(t=Sum('vendor_amount'))['t'] or 0

    tab_history_gross = settled_history.aggregate(t=Sum('gross_amount'))['t'] or 0
    tab_history_commission = settled_history.aggregate(t=Sum('commission_amount'))['t'] or 0
    tab_history_vendor = settled_history.aggregate(t=Sum('vendor_amount'))['t'] or 0

    all_vendors = VendorProfile.objects.all().order_by('company_name')

    from django.contrib import admin
    context = {
        **admin.site.each_context(request),
        'title': 'Earnings & Settlements',
        'vendor_payouts': vendor_payouts,
        'commission_collections': commission_collections,
        'settled_history': settled_history,
        'total_pending_payouts': total_pending_payouts,
        'total_pending_collections': total_pending_collections,
        'total_settled_this_month': total_settled_this_month,
        
        'tab_payouts_gross': tab_payouts_gross,
        'tab_payouts_commission': tab_payouts_commission,
        'tab_payouts_vendor': tab_payouts_vendor,
        
        'tab_collections_gross': tab_collections_gross,
        'tab_collections_commission': tab_collections_commission,
        'tab_collections_vendor': tab_collections_vendor,
        
        'tab_history_gross': tab_history_gross,
        'tab_history_commission': tab_history_commission,
        'tab_history_vendor': tab_history_vendor,
        
        'current_date_filter': date_filter,
        'current_vendor_filter': vendor_filter,
        'all_vendors': all_vendors,
    }
    return TemplateResponse(request, 'admin/app/settlement/changelist.html', context)


def _settings_view(request):
    if not (request.user.is_active and request.user.is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    
    from django.contrib import messages
    from django.shortcuts import redirect
    
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.email = request.POST.get('email', '')
        request.user.save()
        messages.success(request, 'Your admin profile settings have been updated successfully.')
        return redirect('admin:settings')

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
        path('earnings/', self.admin_view(_earnings_view), name='earnings'),
        path('settings/', self.admin_view(_settings_view), name='settings'),
    ]
    return custom_urls + _original_get_urls(self)

admin.AdminSite.get_urls = _custom_get_urls


