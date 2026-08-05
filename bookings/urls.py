from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('room/<int:room_id>/', views.room_detail, name='room_detail'),
    path('book/', views.book_room, name='book_room'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('cancel-booking/<int:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('cancel-recurring/<int:pattern_id>/', views.cancel_recurring, name='cancel_recurring'),

    path('manage/rooms/', views.admin_rooms, name='admin_rooms'),
    path('manage/rooms/add/', views.add_room, name='add_room'),
    path('manage/rooms/edit/<int:room_id>/', views.edit_room, name='edit_room'),
    path('manage/rooms/delete/<int:room_id>/', views.delete_room, name='delete_room'),
    path('manage/bookings/', views.admin_bookings, name='admin_bookings'),
    path('manage/bookings/approve/<int:booking_id>/', views.approve_booking, name='approve_booking'),
    path('manage/bookings/reject/<int:booking_id>/', views.reject_booking, name='reject_booking'),
    path('manage/facilities/', views.admin_facilities, name='admin_facilities'),
    path('manage/facilities/add/', views.add_facility, name='add_facility'),
    path('manage/facilities/delete/<int:facility_id>/', views.delete_facility, name='delete_facility'),
    path('manage/settings/', views.admin_settings, name='admin_settings'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Admin - User Management
    path('manage/users/', views.manage_users, name='manage_users'),
    path('manage/users/add/', views.add_user, name='add_user'),
    path('manage/users/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('manage/users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('manage/users/reset-password/<int:user_id>/', views.reset_password, name='reset_password'),

    path('api/search-users/', views.search_users_api, name='search_users_api'),
    
    path('api/notifications/', views.get_notifications_api, name='get_notifications_api'),
    path('api/notifications/read/<int:notif_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/read-all/', views.mark_all_read, name='mark_all_read'),
    path('manage/audit-log/', views.audit_log, name='audit_log'),
    path('check-in/<int:booking_id>/', views.check_in, name='check_in'),
    path('check-out/<int:booking_id>/', views.check_out, name='check_out'),
    path('submit-review/<int:booking_id>/', views.submit_review, name='submit_review'),
    path('room/<int:room_id>/reviews/', views.room_reviews, name='room_reviews'),
    path('waiting-list/add/', views.add_to_waiting_list, name='add_to_waiting_list'),
    path('my-waiting-list/', views.my_waiting_list, name='my_waiting_list'),
    path('waiting-list/cancel/<int:waiting_id>/', views.cancel_waiting_list, name='cancel_waiting_list'),
    path('download-ics/<int:booking_id>/', views.download_ics, name='download_ics'),
    path('manage/identity/', views.company_identity, name='company_identity'),

]