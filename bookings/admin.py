from django.contrib import admin
from .models import Facility, Room, Booking, Setting


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'capacity', 'created_at']
    list_filter = ['facilities']
    search_fields = ['name']
    filter_horizontal = ['facilities']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'room', 'booking_date', 'start_time', 'end_time', 'status', 'created_at']
    list_filter = ['status', 'booking_date', 'room']
    search_fields = ['user__username', 'room__name', 'purpose']
    date_hierarchy = 'booking_date'


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value']