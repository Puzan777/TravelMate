from django.contrib import admin
from .models import CustomUser, Destination, Package


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    pass


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'city', 'price', 'is_featured', 'is_active')
    search_fields = ('name', 'country', 'city')
    list_filter = ('is_featured', 'is_active')


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price', 'is_hot_sale', 'is_active', 'created_at')
    list_filter = ('category', 'is_hot_sale', 'is_active')
    search_fields = ('title', 'destination__name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_hot_sale', 'is_active')

    fieldsets = (
        (None, {'fields': ('title', 'category', 'image', 'price', 'description', 'destination')}),
        ('Trip info', {'fields': ('duration', 'max_people', 'trip_difficulty', 'activity', 'max_elevation')}),
        ('Logistics', {'fields': ('accommodation', 'meal', 'vehicle')}),
        ('Optional', {'fields': ('major_highlights', 'itinerary')}),
        ('Status', {'fields': ('is_hot_sale', 'is_active')}),
    )