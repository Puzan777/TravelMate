from django.contrib import admin
from .models import CustomUser, Destination, Package, Booking

# Hide default Django admin nav sidebar; custom dashboard provides navigation.
admin.site.enable_nav_sidebar = False


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    pass


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


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price', 'rating', 'is_hot_sale', 'is_active', 'created_at')
    list_filter = ('category', 'is_hot_sale', 'is_active')
    search_fields = ('title', 'slug', 'destination__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_hot_sale', 'is_active')

    fieldsets = (
        (None, {'fields': ('title', 'slug', 'category', 'image', 'price', 'rating', 'description', 'destination')}),
        ('Trip info', {'fields': ('duration', 'max_people', 'trip_difficulty', 'activity', 'max_elevation')}),
        ('Logistics', {'fields': ('accommodation', 'meal', 'vehicle')}),
        ('Optional', {'fields': ('major_highlights', 'itinerary')}),
        ('Status', {'fields': ('is_hot_sale', 'is_active')}),
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('package', 'user', 'travel_date', 'created_at')
    list_filter = ('travel_date', 'created_at')
    search_fields = ('package__title', 'user__username')
    readonly_fields = ('created_at',)