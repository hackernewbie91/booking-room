from urllib.parse import urlencode
from datetime import datetime
from django.utils import timezone


def generate_google_calendar_link(booking):
    """Generate link untuk menambahkan booking ke Google Calendar."""
    start_naive = datetime.combine(booking.booking_date, booking.start_time)
    end_naive = datetime.combine(booking.booking_date, booking.end_time)
    
    start = timezone.make_aware(start_naive) if timezone.is_naive(start_naive) else start_naive
    end = timezone.make_aware(end_naive) if timezone.is_naive(end_naive) else end_naive
    
    params = {
        'action': 'TEMPLATE',
        'text': f'{booking.purpose or "Meeting"} - {booking.room.name}',
        'dates': f'{start.strftime("%Y%m%dT%H%M%S")}/{end.strftime("%Y%m%dT%H%M%S")}',
        'details': f'Ruangan: {booking.room.name}\nPemesan: {booking.user.username}',
        'location': booking.room.name,
        'sf': 'true',
        'output': 'xml',
    }
    return f'https://calendar.google.com/calendar/render?{urlencode(params)}'


def generate_outlook_calendar_link(booking):
    """Generate link untuk menambahkan booking ke Outlook Calendar."""
    start_naive = datetime.combine(booking.booking_date, booking.start_time)
    end_naive = datetime.combine(booking.booking_date, booking.end_time)
    
    start = timezone.make_aware(start_naive) if timezone.is_naive(start_naive) else start_naive
    end = timezone.make_aware(end_naive) if timezone.is_naive(end_naive) else end_naive
    
    params = {
        'subject': f'{booking.purpose or "Meeting"} - {booking.room.name}',
        'startdt': start.strftime('%Y-%m-%dT%H:%M:%S'),
        'enddt': end.strftime('%Y-%m-%dT%H:%M:%S'),
        'body': f'Ruangan: {booking.room.name}<br>Pemesan: {booking.user.username}',
        'location': booking.room.name,
        'path': '/calendar/action/compose',
        'rru': 'addevent',
    }
    return f'https://outlook.live.com/calendar/0/deeplink/compose?{urlencode(params)}'


def generate_ics_content(booking):
    """Generate konten file .ics untuk di-download."""
    start_naive = datetime.combine(booking.booking_date, booking.start_time)
    end_naive = datetime.combine(booking.booking_date, booking.end_time)
    
    start = timezone.make_aware(start_naive) if timezone.is_naive(start_naive) else start_naive
    end = timezone.make_aware(end_naive) if timezone.is_naive(end_naive) else end_naive
    
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//RoomBooking//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
DTSTART:{start.strftime("%Y%m%dT%H%M%S")}
DTEND:{end.strftime("%Y%m%dT%H%M%S")}
SUMMARY:{booking.purpose or "Meeting"} - {booking.room.name}
DESCRIPTION:Ruangan: {booking.room.name}\\nPemesan: {booking.user.username}
LOCATION:{booking.room.name}
UID:{booking.id}@roombooking
DTSTAMP:{timezone.now().strftime("%Y%m%dT%H%M%S")}
END:VEVENT
END:VCALENDAR"""
    
    return ics_content
