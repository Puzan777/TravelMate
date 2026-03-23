from django.contrib import admin
from .models import CustomUser, Destination, Package, Booking, Inquiry, HotSale

# Hide default Django admin nav sidebar; custom dashboard provides navigation.
admin.site.enable_nav_sidebar = False


def _current_vendor_profile(user):
    return getattr(user, 'vendor_profile', None)


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    pass


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'best_season', 'created_at')
    search_fields = ('name', 'short_description', 'visa_info', 'safety_note')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('vendor', 'name', 'hero_image', 'short_description')}),
        ('Travel Info', {'fields': ('best_season', 'visa_info', 'safety_note')}),
        ('System', {'fields': ('created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        vendor_profile = _current_vendor_profile(request.user)
        if vendor_profile:
            return qs.filter(vendor=vendor_profile)
        return qs.none()

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            vendor_profile = _current_vendor_profile(request.user)
            if vendor_profile and obj.vendor_id is None:
                obj.vendor = vendor_profile
        super().save_model(request, obj, form, change)


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
        if db_field.name == 'destination' and not request.user.is_superuser:
            vendor_profile = _current_vendor_profile(request.user)
            if vendor_profile:
                kwargs['queryset'] = Destination.objects.filter(vendor=vendor_profile).order_by('name')
            else:
                kwargs['queryset'] = Destination.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            vendor_profile = _current_vendor_profile(request.user)
            if vendor_profile and obj.vendor_id is None:
                obj.vendor = vendor_profile
        super().save_model(request, obj, form, change)


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


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('package', 'user', 'travel_date', 'created_at')
    list_filter = ('travel_date', 'created_at')
    search_fields = ('package__title', 'user__username')
    readonly_fields = ('created_at',)

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
