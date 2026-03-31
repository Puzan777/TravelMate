from django.contrib import admin
from .models import Booking, CustomUser, Destination, HotSale, Inquiry, Package, PackageItinerary

# Hide default Django admin nav sidebar; custom dashboard provides navigation.
admin.site.enable_nav_sidebar = False


def _current_vendor_profile(user):
    return getattr(user, 'vendor_profile', None)


def _is_platform_admin(user):
    return user.is_active and user.is_staff and not getattr(user, 'is_vendor', False)


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'is_superuser', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email')


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


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'vendor', 'category', 'price', 'rating', 'is_active', 'created_at')
    list_filter = ('vendor', 'category', 'is_active')
    search_fields = ('title', 'slug', 'destination__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active',)

    fieldsets = (
        (None, {'fields': ('vendor', 'title', 'slug', 'category', 'image', 'price', 'rating', 'description', 'destination')}),
        ('Trip info', {'fields': ('duration', 'max_people', 'trip_difficulty', 'activity', 'max_elevation')}),
        ('Logistics', {'fields': ('accommodation', 'meal', 'vehicle')}),
        ('Optional', {'fields': ('major_highlights', 'itinerary')}),
        ('Status', {'fields': ('is_active',)}),
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


@admin.register(HotSale)
class HotSaleAdmin(admin.ModelAdmin):
    list_display = ('package', 'original_price', 'sale_price', 'savings', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('package__title', 'package__slug', 'note')
    autocomplete_fields = ('package',)
    readonly_fields = ('original_price', 'created_at', 'updated_at')
    fieldsets = (
        ('Hot Sale', {'fields': ('package', 'original_price', 'sale_price', 'note', 'is_active')}),
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
        return formfield

    @admin.display(description='Original Price')
    def original_price(self, obj):
        if not obj:
            return 'Select a package to preview the original price.'
        return obj.package.price

    @admin.display(description='Savings')
    def savings(self, obj):
        return obj.savings_amount

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
    list_display = ('package', 'full_name', 'email', 'phone', 'number_of_people', 'travel_date', 'created_at')
    list_filter = ('travel_date', 'created_at')
    search_fields = ('package__title', 'user__username', 'full_name', 'email', 'phone', 'nationality', 'pickup_location')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Booking', {'fields': ('package', 'user', 'travel_date', 'number_of_people')}),
        ('Traveler', {'fields': ('full_name', 'email', 'phone', 'nationality', 'emergency_contact', 'pickup_location')}),
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


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
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
