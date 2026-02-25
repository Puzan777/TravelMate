from django.contrib import admin
from .models import CustomUser, Destination, Package


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    pass


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    search_fields = ('name',)
    list_filter = ('is_active',)
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price', 'is_hot_sale', 'is_active', 'created_at')
    list_filter = ('category', 'is_hot_sale', 'is_active')
    search_fields = ('title', 'slug', 'destination__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_hot_sale', 'is_active')

    fieldsets = (
        (None, {'fields': ('title', 'slug', 'category', 'image', 'price', 'description', 'destination')}),
        ('Trip info', {'fields': ('duration', 'max_people', 'trip_difficulty', 'activity', 'max_elevation')}),
        ('Logistics', {'fields': ('accommodation', 'meal', 'vehicle')}),
        ('Optional', {'fields': ('major_highlights', 'itinerary')}),
        ('Status', {'fields': ('is_hot_sale', 'is_active')}),
    )