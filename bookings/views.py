from django.db.models import Q
import threading
from asgiref.sync import async_to_sync
from datetime import datetime
from channels.layers import get_channel_layer
from django.db import models
from datetime import date, datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponseForbidden
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.http import JsonResponse
from django.urls import reverse
from urllib.parse import urlencode
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import concurrent.futures
from .models import RoomReview
from .models import Room, Booking, Facility, Setting, RecurringPattern
from .models import Notification
from .models import AuditLog
from .models import WaitingList
from .calendar_utils import generate_google_calendar_link, generate_outlook_calendar_link, generate_ics_content


def is_admin(user):
    return user.is_superuser


@login_required
def search_users_api(request):
    #API untuk auto-suggest user berdasarkan username/email
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    from django.contrib.auth.models import User
    users = User.objects.filter(
        models.Q(username__icontains=query) | models.Q(email__icontains=query)
    )[:10]
    
    results = []
    for u in users:
        results.append({
            'username': u.username,
            'email': u.email or u.username + '@example.com',
            'display': f"{u.username} <{u.email or u.username + '@example.com'}>"
        })
    
    return JsonResponse(results, safe=False)


def get_approval_mode():
    obj = Setting.objects.filter(key='approval_mode').first()
    return obj.value == 'on' if obj else False


def send_booking_notification(booking, participants):
    subject = f"Undangan Meeting: {booking.purpose or 'Tanpa Judul'} - {booking.room.name}"
    
    google_link = generate_google_calendar_link(booking)
    outlook_link = generate_outlook_calendar_link(booking)
    
    # Format HTML untuk email
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1e3a8a;">📋 Undangan Meeting</h2>
        <p>Halo,</p>
        <p>Anda diundang dalam meeting:</p>
        
        <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
            <tr>
                <td style="padding: 8px 0; width: 150px; font-weight: bold; color: #475569;">📅 Tanggal</td>
                <td style="padding: 8px 0;">{booking.booking_date.strftime('%d %B %Y')}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #475569;">⏰ Jam</td>
                <td style="padding: 8px 0;">{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #475569;">🏢 Ruangan</td>
                <td style="padding: 8px 0;">{booking.room.name}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #475569;">📝 Tujuan</td>
                <td style="padding: 8px 0;">{booking.purpose or '-'}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #475569;">👤 Pemesan</td>
                <td style="padding: 8px 0;">{booking.user.username}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #475569;">🔄 Berulang</td>
                <td style="padding: 8px 0;">{'Ya' if booking.recurring_pattern else 'Tidak'}</td>
            </tr>
        </table>
        
        <div style="margin-top: 20px; padding: 16px; background: #f1f5f9; border-radius: 8px;">
            <p style="font-weight: bold; color: #1e3a8a;">📅 Tambahkan ke Kalender:</p>
            <p>• <a href="{google_link}" style="color: #4285f4;">Google Calendar</a></p>
            <p>• <a href="{outlook_link}" style="color: #0078d4;">Outlook Calendar</a></p>
        </div>
        
        <p style="margin-top: 20px; color: #475569;">Harap hadir tepat waktu.</p>
        <p style="color: #94a3b8; font-size: 0.9rem;">Salam,<br>RoomBooking System</p>
    </div>
    """
    
    # Plain text fallback (untuk email client yang tidak mendukung HTML)
    plain_body = f"""
Halo,

Anda diundang dalam meeting:

📅 Tanggal  : {booking.booking_date.strftime('%d %B %Y')}
⏰ Jam      : {booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}
🏢 Ruangan  : {booking.room.name}
📝 Tujuan   : {booking.purpose or '-'}
👤 Pemesan  : {booking.user.username}
🔄 Berulang : {'Ya' if booking.recurring_pattern else 'Tidak'}

📅 Tambahkan ke Kalender:
• Google Calendar: {google_link}
• Outlook: {outlook_link}

Harap hadir tepat waktu.

Salam,
RoomBooking System
"""
    
    try:
        for email in participants:
            send_mail(
                subject=subject,
                message=plain_body,        # fallback untuk client non-HTML
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email.strip()],
                html_message=html_body,    # versi HTML utama
                fail_silently=False,
            )
            print(f"✅ Email terkirim ke {email}")
    except Exception as e:
        print(f"❌ Email error: {e}")


def check_conflict(room, booking_date, start_time, end_time, exclude_booking_id=None):
    query = room.bookings.filter(
        booking_date=booking_date,
        status__in=['confirmed', 'pending'],
        start_time__lt=end_time,
        end_time__gt=start_time
    )
    if exclude_booking_id:
        query = query.exclude(id=exclude_booking_id)
    return query.first()


def create_single_booking(user, room, booking_date, start_time, end_time, purpose, status, recurring_pattern=None):
    conflict = check_conflict(room, booking_date, start_time, end_time)
    if conflict:
        return None, f"Bentrok dengan booking lain ({conflict.start_time.strftime('%H:%M')}-{conflict.end_time.strftime('%H:%M')})"
    
    # Validasi jam mulai tidak boleh lewat jika booking untuk hari ini
    now = timezone.localtime()
    if booking_date == now.date() and start_time <= now.time():
        return None, 'Tidak bisa booking untuk jam yang sudah lewat.'

    booking = Booking.objects.create(
        user=user,
        room=room,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        purpose=purpose,
        status=status,
        recurring_pattern=recurring_pattern
    )

    # Buat notifikasi untuk user yang booking
    current_time = timezone.localtime(timezone.now()).strftime('%d/%m %H:%M')
    create_notification(user, f'[{current_time}] Booking berhasil: {room.name} ({booking_date.strftime("%d/%m")}, {start_time.strftime("%H:%M")}-{end_time.strftime("%H:%M")})', booking)

    # Kirim WebSocket ke semua admin
    for admin in User.objects.filter(is_superuser=True):
        if admin != user:
            current_time = timezone.localtime(timezone.now()).strftime('%d/%m %H:%M')
            create_notification(admin, f'[{current_time}] Booking baru: {user.username} memesan {room.name}', booking)
            send_websocket_notification(admin.id, {
                'unread_count': Notification.objects.filter(user=admin, is_read=False).count(),
                'notifications': [{
                    'id': booking.id,
                    'message': f'Booking baru: {user.username} memesan {room.name}',
                    'created_at': timezone.localtime(booking.created_at).strftime('%d/%m %H:%M'),
                    'is_read': False
                }]
            })

    # Kirim notifikasi ke semua admin
    for admin in User.objects.filter(is_superuser=True):
        if admin.id != user.id:
            
            send_websocket_notification(admin.id, {
                'unread_count': Notification.objects.filter(user=admin, is_read=False).count(),
                'notifications': [
                    {
                        'id': booking.id,
                        'message': f'Booking baru: {user.username} memesan {room.name}',
                        'created_at': timezone.localtime(booking.created_at).strftime('%d/%m %H:%M'),
                        'is_read': False
                    }
                ]
            })

    return booking, None


def generate_recurring_dates(start_date, end_date, frequency, interval, days_of_week):
    dates = []
    current = start_date
    while current <= end_date:
        if frequency == 'daily':
            dates.append(current)
            current += timedelta(days=interval)
        elif frequency == 'weekly':
            if days_of_week:
                weekday = str(current.weekday())
                if weekday in days_of_week.split(','):
                    dates.append(current)
                current += timedelta(days=1)
            else:
                dates.append(current)
                current += timedelta(weeks=interval)
        elif frequency == 'biweekly':
            dates.append(current)
            current += timedelta(weeks=2 * interval)
        elif frequency == 'monthly':
            dates.append(current)
            month = current.month + interval
            year = current.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current.day, 28)
            current = date(year, month, day)
        else:
            break
    return dates


def index(request):
    rooms = Room.objects.all()
    now = timezone.localtime()
    current_time = now.time()
    today = now.date()
    room_status = {}
    
    for room in rooms:
        bookings_today = room.bookings.filter(
            booking_date=today,
            status='confirmed'  # <-- HANYA confirmed
        ).order_by('start_time')
        
        if not bookings_today.exists():
            status = 'available'
            status_text = 'Tersedia'
        else:
            ongoing = False
            ongoing_no_checkin = False     # <-- tambahan
            all_past = True
            upcoming_count = 0
            
            for b in bookings_today:
                if b.start_time <= current_time <= b.end_time:
                    if b.checked_in_at is not None:   # <-- cek check‑in
                        ongoing = True
                    else:
                        ongoing_no_checkin = True
                    all_past = False
                if b.end_time > current_time:
                    all_past = False
                if b.start_time > current_time:
                    upcoming_count += 1
            
            if ongoing:
                last_booking = bookings_today.last()
                if current_time < last_booking.end_time:
                    status = 'ongoing'
                    status_text = f'Sedang Dipakai • {upcoming_count} slot berikutnya'
                else:
                    status = 'ongoing_free'
                    status_text = 'Sedang Dipakai • Ada slot kosong'
            elif ongoing_no_checkin:
                last_booking = bookings_today.last()
                if current_time < last_booking.end_time:
                    status = 'ongoing_no_checkin'
                    status_text = f'Sedang Dipakai • {upcoming_count} slot berikutnya (Belum Check-in)'
                else:
                    status = 'ongoing_no_checkin'
                    status_text = 'Sedang Dipakai • Ada slot kosong (Belum Check-in)'
            elif all_past:
                status = 'available'
                status_text = 'Tersedia'
            else:
                status = 'partial'
                status_text = f'Tersedia • {len(bookings_today)} slot terpakai hari ini'
        
        room_status[room.id] = {
            'status': status,
            'text': status_text
        }
    
    return render(request, 'bookings/index.html', {
        'rooms': rooms,
        'room_status': room_status,
    })


def register_view(request):
    from .forms import RegisterForm
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registrasi berhasil! Selamat datang.')
            return redirect('index')
    else:
        form = RegisterForm()
    return render(request, 'bookings/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        from .forms import LoginForm
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Selamat datang, {user.username}!')
                log_activity(request, 'login', 'User', user.id, 
                            f"User {user.username} login")
                return redirect('index')
            else:
                messages.error(request, 'Username atau password salah.')
    else:
        from .forms import LoginForm
        form = LoginForm()
    return render(request, 'bookings/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'Anda telah logout.')
    if request.user.is_authenticated:
        log_activity(request, 'logout', 'User', request.user.id, 
                    f"User {request.user.username} logout")
    return redirect('index')


def send_websocket_notification(user_id, data):
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                'type': 'send_notification',
                'data': data
            }
        )
    except Exception as e:
        print(f"WebSocket error: {e}")
        

def create_notification(user, message, booking=None):

    notif = Notification(
        user=user,
        message=message,
        booking=booking,
    )
    # Simpan waktu lokal secara eksplisit
    notif.created_at = timezone.localtime(timezone.now())
    notif.save()
    return notif
    
def log_activity(request, action, model_name, object_id=None, description=""):
    ip = request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model_name=model_name,
        object_id=object_id,
        description=description,
        ip_address=ip
    )
    
    
def is_within_working_hours(booking_date, start_time, end_time):
 
    mode = Setting.objects.filter(key='working_hours_mode').first()
    if not mode or mode.value == 'free':
        return True, None  # Mode bebas, selalu boleh
    
    # Mode jam kerja
    work_days = Setting.objects.filter(key='work_days').first()
    allowed_days = work_days.value.split(',') if work_days else ['0','1','2','3','4']
    
    work_start = Setting.objects.filter(key='work_start').first()
    work_start_time = datetime.strptime(work_start.value if work_start else '08:00', '%H:%M').time()
    
    work_end = Setting.objects.filter(key='work_end').first()
    work_end_time = datetime.strptime(work_end.value if work_end else '17:00', '%H:%M').time()
    
    # Cek hari
    weekday = str(booking_date.weekday())
    if weekday not in allowed_days:
        day_names = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
        return False, f'Booking hanya bisa di hari {", ".join([day_names[int(d)] for d in allowed_days])}.'
    
    # Cek jam
    if start_time < work_start_time or end_time > work_end_time:
        return False, f'Booking hanya bisa di jam {work_start_time.strftime("%H:%M")} - {work_end_time.strftime("%H:%M")}.'
    
    return True, None


def global_context(request):
    """Context processor untuk logo dan nama perusahaan."""
    from .models import Setting
    logo = Setting.objects.filter(key='company_logo').first()
    logo_url = None
    if logo and logo.value:
        logo_url = f'/media/logo/{logo.value}'
    
    company_name = Setting.objects.filter(key='company_name').first()
    company_name = company_name.value if company_name else ''
    
    return {
        'logo_url': logo_url,
        'company_name': company_name,
    }


# ---------- Booking ----------
@login_required
def room_detail(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    selected_date = request.GET.get('date')
    bookings_today = []
    total_booked_hours = 0
    now = timezone.localtime()
    current_time = now.time()
    
    if selected_date:
        try:
            dt = datetime.strptime(selected_date, '%Y-%m-%d').date()
            bookings_today = room.bookings.filter(
                booking_date=dt,
                status='confirmed'
            ).order_by('start_time')
            
            for b in bookings_today:
                # Hitung durasi
                start_dt = datetime.combine(dt, b.start_time)
                end_dt = datetime.combine(dt, b.end_time)
                duration = end_dt - start_dt
                total_booked_hours += duration.total_seconds() / 3600
                b.duration = f"{int(duration.total_seconds() // 3600)}j {int((duration.total_seconds() % 3600) // 60)}m"
                
                # Tambahkan status waktu
                if dt < now.date():
                    b.time_status = 'past'  # Sudah lewat
                elif dt == now.date():
                    if b.end_time < current_time:
                        b.time_status = 'past'  # Sudah selesai
                    elif b.start_time <= current_time <= b.end_time:
                        if b.checked_in_at is not None:
                            b.time_status = 'ongoing'  # Sedang berlangsung, sudah check-in
                        else:
                            b.time_status = 'ongoing_no_checkin'  # Sedang berlangsung, belum check-in
                    else:
                        b.time_status = 'upcoming'  # Akan datang
                else:
                    b.time_status = 'upcoming'  # Tanggal besok/depan
                    
        except ValueError:
            pass

    # ===== TAMBAHKAN DI SINI =====
    # Tambahkan link kalender untuk setiap booking
    from .calendar_utils import generate_google_calendar_link, generate_outlook_calendar_link
    
    for b in bookings_today:
        if b.status == 'confirmed':
            b.google_calendar_link = generate_google_calendar_link(b)
            b.outlook_calendar_link = generate_outlook_calendar_link(b)
    # ===== SAMPAI SINI =====
    
    return render(request, 'bookings/room_detail.html', {
        'room': room,
        'selected_date': selected_date,
        'bookings_today': bookings_today,
        'total_booked_hours': round(total_booked_hours, 1),
        'today': date.today().isoformat(),
    })


@login_required
def book_room(request):
    if request.method == 'POST':
        room_id = request.POST.get('room_id')
        booking_date = request.POST.get('booking_date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        purpose = request.POST.get('purpose', '')
        participants = request.POST.get('participants', '')
        print(f"DEBUG participants: '{participants}'")
        is_recurring = request.POST.get('is_recurring') == 'on'

        try:
            room = get_object_or_404(Room, id=room_id)
            d = datetime.strptime(booking_date, '%Y-%m-%d').date()
            start_t = datetime.strptime(start_time, '%H:%M').time()
            end_t = datetime.strptime(end_time, '%H:%M').time()

            if d < date.today():
                messages.error(request, 'Tidak bisa booking untuk tanggal yang sudah lewat.')
                return redirect(f"/room/{room_id}/?date={booking_date}")

            # Tambahan
            if d == date.today() and start_t <= timezone.localtime().time():
                messages.error(request, 'Tidak bisa booking untuk jam yang sudah lewat.')
                return redirect(f'/room/{room_id}/?date={booking_date}')

            if start_t >= end_t:
                messages.error(request, 'Jam selesai harus lebih besar dari jam mulai.')
                return redirect(f"/room/{room_id}/?date={booking_date}")
            
            # ===== TAMBAHKAN DI SINI =====
            # Validasi jam kerja
            allowed, error_msg = is_within_working_hours(d, start_t, end_t)
            if not allowed:
                messages.error(request, error_msg)
                return redirect(f'/room/{room_id}/?date={booking_date}')
            # ===== SAMPAI SINI =====

            status = 'pending' if get_approval_mode() else 'confirmed'

            if is_recurring:
                frequency = request.POST.get('frequency', 'weekly')
                interval = int(request.POST.get('interval', 1))
                end_date_str = request.POST.get('end_date')
                days_of_week = request.POST.get('days_of_week', '')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

                if end_date <= d:
                    messages.error(request, 'Tanggal akhir harus lebih besar dari tanggal mulai.')
                    return redirect(f"/room/{room_id}/?date={booking_date}")

                pattern = RecurringPattern.objects.create(
                    user=request.user,
                    room=room,
                    start_time=start_t,
                    end_time=end_t,
                    start_date=d,
                    end_date=end_date,
                    frequency=frequency,
                    interval=interval,
                    days_of_week=days_of_week,
                    purpose=purpose
                )

                dates = generate_recurring_dates(d, end_date, frequency, interval, days_of_week)
                success_count = 0
                failed_dates = []

                for dt in dates:
                    booking, error = create_single_booking(
                        request.user, room, dt, start_t, end_t, purpose, status, pattern
                    )
                    if booking:
                        success_count += 1
                        # ===== TAMBAHKAN DI SINI =====
                        # Notifikasi untuk recurring booking
                        current_time = timezone.localtime(timezone.now()).strftime('%d/%m %H:%M')
                        create_notification(request.user, f'[{current_time}] Booking berulang: {room.name} ({dt.strftime("%d/%m")}, {start_t.strftime("%H:%M")}-{end_t.strftime("%H:%M")})', booking)
                        
                        for admin in User.objects.filter(is_superuser=True):
                            if admin != request.user:
                                current_time = timezone.localtime(timezone.now()).strftime('%d/%m %H:%M')
                                create_notification(admin, f'[{current_time}] Booking berulang: {request.user.username} memesan {room.name}', booking)
                                
                                data = {
                                    'unread_count': Notification.objects.filter(user=admin, is_read=False).count(),
                                    'notifications': [{
                                        'id': booking.id,
                                        'message': f'Booking berulang: {request.user.username} memesan {room.name}',
                                        'created_at': timezone.localtime(booking.created_at).strftime('%d/%m %H:%M'),
                                        'is_read': False
                                    }]
                                }
                                
                                threading.Thread(
                                    target=send_websocket_notification,
                                    args=(admin.id, data)
                                ).start()
                        # ===== SAMPAI SINI =====
                    else:
                        failed_dates.append(dt.strftime('%Y-%m-%d'))

                if failed_dates:
                    messages.warning(
                        request,
                        f'{success_count} booking berhasil. {len(failed_dates)} gagal karena bentrok: {", ".join(failed_dates[:5])}'
                    )
                else:
                    messages.success(request, f'{success_count} booking berulang berhasil dibuat!')
            else:
                booking, error = create_single_booking(
                    request.user, room, d, start_t, end_t, purpose, status
                )
                if booking:
                    messages.success(request, 'Booking berhasil!')
                    # ===== TAMBAHKAN 2 BARIS INI =====
                    if participants:
                        booking.participants = participants
                        booking.save(update_fields=['participants'])
                    # ================================
                    log_activity(request, 'create', 'Booking', booking.id, 
                                f"User {request.user.username} membooking {room.name} pada {d} ({start_t}-{end_t})")
                    
                    # Kirim notifikasi ke semua admin
                    for admin in User.objects.filter(is_superuser=True):
                        if admin != request.user:
                            
                            data = {
                                'unread_count': Notification.objects.filter(user=admin, is_read=False).count(),
                                'notifications': [{
                                    'id': booking.id,
                                    'message': f'Booking baru: {request.user.username} memesan {room.name}',
                                    'created_at': timezone.localtime(booking.created_at).strftime('%d/%m %H:%M'),
                                    'is_read': False
                                }]
                            }
                            
                            # Kirim via thread agar tidak blocking
                            threading.Thread(
                                target=send_websocket_notification,
                                args=(admin.id, data)
                            ).start()
                    # ===== SAMPAI SINI =====
                    
                    # Kirim email berdasarkan mode persetujuan
                    if participants:
                        if not get_approval_mode():
                            # Mode OFF: langsung kirim
                            participant_list = [p.strip() for p in participants.split(',') if p.strip()]
                            if participant_list:
                                threading.Thread(
                                    target=send_booking_notification,
                                    args=(booking, participant_list),
                                    daemon=True
                                ).start()
                                print(f"📧 Email langsung dikirim ke {len(participant_list)} peserta")
                        else:
                            # Mode ON: simpan peserta, nanti kirim saat approve
                            print("📧 Mode persetujuan ON, email akan dikirim setelah admin approve")
                    
                else:
                    messages.error(request, error)

        except Exception as e:
            messages.error(request, f'Gagal booking: {str(e)}')

        return redirect(f"/room/{room_id}/?date={booking_date}")

    return redirect('index')


@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).order_by('-booking_date', '-created_at')
    recurring_patterns = RecurringPattern.objects.filter(user=request.user, status='active').order_by('-created_at')
    
    # Auto check-out untuk booking user yang sedang login
    now = timezone.now()
    auto_checkout = Booking.objects.filter(
        user=request.user,
        status='confirmed',
        checked_in_at__isnull=False,
        checked_out_at__isnull=True
    ).filter(
        Q(booking_date__lt=now.date()) |
        Q(booking_date=now.date(), end_time__lt=now.time())
    )

    for b in auto_checkout:
        b.checked_out_at = now
        b.save()

    # Tandai booking yang sudah expired
    now = timezone.now()
    for b in bookings:
        booking_end = datetime.combine(b.booking_date, b.end_time)
        booking_end = timezone.make_aware(booking_end) if not timezone.is_aware(booking_end) else booking_end
        b.is_expired = booking_end < now

    # ===== TAMBAHKAN KODE BARU DI SINI =====
    # Tambahkan link kalender untuk setiap booking
    from .calendar_utils import generate_google_calendar_link, generate_outlook_calendar_link

    for b in bookings:
        if b.status == 'confirmed':
            b.google_calendar_link = generate_google_calendar_link(b)
            b.outlook_calendar_link = generate_outlook_calendar_link(b)
    # ===== SAMPAI SINI =====

    # Auto-reject Pending yang sudah lewat
    now = timezone.now()
    expired_pending = Booking.objects.filter(
        user=request.user,
        status='pending'
    ).filter(
        Q(booking_date__lt=now.date()) |
        Q(booking_date=now.date(), end_time__lt=now.time())
    )

    for b in expired_pending:
        b.status = 'rejected'
        b.rejection_reason = 'Otomatis ditolak: Waktu booking sudah terlewat.'
        b.save()

    return render(request, 'bookings/my_bookings.html', {
        'bookings': bookings,
        'recurring_patterns': recurring_patterns,
        'today': date.today(),
    })


@login_required
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if booking.user != request.user and not is_admin(request.user):
        return HttpResponseForbidden("Tidak diizinkan.")
    if booking.status not in ['confirmed', 'pending']:
        messages.warning(request, 'Booking ini tidak dapat dibatalkan.')
        return redirect('my_bookings')
    booking.delete()

    # Setelah booking dihapus, cek waiting list untuk slot yang sama
    waiting = WaitingList.objects.filter(
        room=booking.room,
        booking_date=booking.booking_date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        status='waiting'
    ).order_by('created_at').first()

    if waiting:
        # Buat booking untuk user waiting list
        new_booking = Booking.objects.create(
            user=waiting.user,
            room=booking.room,
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            purpose=waiting.purpose,
            status='confirmed'
        )
        waiting.status = 'converted'
        waiting.save()
        
        # Notifikasi ke user yang dapat slot
        create_notification(
            waiting.user,
            f'[{timezone.localtime(timezone.now()).strftime("%d/%m %H:%M")}] Slot tersedia! Booking otomatis dibuat: {booking.room.name} ({booking.booking_date.strftime("%d/%m")}, {booking.start_time.strftime("%H:%M")}-{booking.end_time.strftime("%H:%M")})',
            new_booking
        )
        log_activity(request, 'system', 'Booking', new_booking.id, 
                    f"Auto-booking dari waiting list: {waiting.user.username} untuk {booking.room.name}")

    messages.info(request, 'Booking dibatalkan.')
    return redirect('my_bookings')


@login_required
def cancel_recurring(request, pattern_id):
    pattern = get_object_or_404(RecurringPattern, id=pattern_id)
    if pattern.user != request.user and not is_admin(request.user):
        return HttpResponseForbidden("Tidak diizinkan.")
    pattern.bookings.filter(status__in=['confirmed', 'pending']).delete()
    pattern.status = 'stopped'
    pattern.save()
    messages.info(request, 'Semua booking berulang dibatalkan.')
    return redirect('my_bookings')

@login_required
def get_notifications_api(request):
    notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:20]
    unread_count = notifications.count()
    
    return JsonResponse({
        'unread_count': unread_count,
        'notifications': [
            {
                'id': n.id,
                'message': n.message,
                'created_at': timezone.localtime(n.created_at).strftime('%d/%m %H:%M'),
                'is_read': n.is_read
            } for n in notifications
        ]
    })

@login_required
def mark_notification_read(request, notif_id):
    if request.method == 'POST':
        try:
            notif = Notification.objects.get(id=notif_id, user=request.user)
            notif.is_read = True
            notif.save()
            return JsonResponse({'success': True})
        except Notification.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'})
    return JsonResponse({'success': False})

@login_required
def mark_all_read(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
def check_in(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    # Hanya user yang booking atau admin yang bisa check-in
    if booking.user != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Tidak diizinkan.")
    if booking.checked_in_at:
        messages.warning(request, 'Anda sudah check-in.')
    else:
        booking.checked_in_at = timezone.now()
        booking.save()
        messages.success(request, 'Check-in berhasil!')
    return redirect('my_bookings')

@login_required
def check_out(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if booking.user != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Tidak diizinkan.")
    if booking.checked_out_at:
        messages.warning(request, 'Anda sudah check-out.')
    else:
        booking.checked_out_at = timezone.now()
        booking.save()
        messages.success(request, 'Check-out berhasil!')
    return redirect('my_bookings')


@login_required
def submit_review(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, user=request.user)
    
    # Cek apakah sudah ada review
    if hasattr(booking, 'review'):
        messages.warning(request, 'Anda sudah memberikan review untuk booking ini.')
        return redirect('my_bookings')
    
    # Cek apakah booking sudah selesai (checked_out atau lewat waktu)
    now = timezone.now()
    booking_end = timezone.make_aware(datetime.combine(booking.booking_date, booking.end_time))
    
    if booking_end > now and not booking.checked_out_at:
        messages.warning(request, 'Anda hanya bisa memberikan review setelah meeting selesai.')
        return redirect('my_bookings')
    
    if request.method == 'POST':
        rating = int(request.POST.get('rating', 5))
        comment = request.POST.get('comment', '').strip()
        
        RoomReview.objects.create(
            booking=booking,
            user=request.user,
            room=booking.room,
            rating=rating,
            comment=comment
        )
        
        messages.success(request, 'Terima kasih atas review Anda!')
        return redirect('my_bookings')
    
    return render(request, 'bookings/submit_review.html', {
        'booking': booking,
        'room': booking.room,
    })


@login_required
def room_reviews(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    reviews = room.reviews.all().order_by('-created_at')
    
    avg_rating = reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0
    
    return render(request, 'bookings/room_reviews.html', {
        'room': room,
        'reviews': reviews,
        'avg_rating': round(avg_rating, 1),
    })

# Waiting list function
@login_required
def add_to_waiting_list(request):
    if request.method == 'POST':
        room_id = request.POST.get('room_id')
        booking_date = request.POST.get('booking_date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        purpose = request.POST.get('purpose', '')
        
        try:
            room = get_object_or_404(Room, id=room_id)
            d = datetime.strptime(booking_date, '%Y-%m-%d').date()
            start_t = datetime.strptime(start_time, '%H:%M').time()
            end_t = datetime.strptime(end_time, '%H:%M').time()
            
            # Cek apakah sudah ada di waiting list
            existing = WaitingList.objects.filter(
                user=request.user,
                room=room,
                booking_date=d,
                start_time=start_t,
                end_time=end_t,
                status='waiting'
            ).first()
            
            if existing:
                messages.warning(request, 'Anda sudah masuk waiting list untuk slot ini.')
            else:
                WaitingList.objects.create(
                    user=request.user,
                    room=room,
                    booking_date=d,
                    start_time=start_t,
                    end_time=end_t,
                    purpose=purpose,
                    status='waiting'
                )
                messages.success(request, f'Anda telah masuk waiting list untuk {room.name} pada {d.strftime("%d/%m")} ({start_t.strftime("%H:%M")}-{end_t.strftime("%H:%M")}).')
        except Exception as e:
            messages.error(request, f'Gagal masuk waiting list: {str(e)}')
        
        return redirect(f'/room/{room_id}/?date={booking_date}')
    
    return redirect('index')


@login_required
def my_waiting_list(request):
    waiting_items = WaitingList.objects.filter(user=request.user, status='waiting').order_by('-created_at')
    return render(request, 'bookings/my_waiting_list.html', {'waiting_items': waiting_items})


@login_required
def cancel_waiting_list(request, waiting_id):
    item = get_object_or_404(WaitingList, id=waiting_id, user=request.user)
    if item.status == 'waiting':
        item.status = 'expired'
        item.save()
        messages.info(request, 'Anda telah keluar dari waiting list.')
    return redirect('my_waiting_list')

@login_required
def download_ics(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, user=request.user)
    
    ics_content = generate_ics_content(booking)
    
    response = HttpResponse(ics_content, content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="booking_{booking.id}.ics"'
    return response


# ---------- Admin Views ----------
@login_required
@user_passes_test(is_admin)
def admin_rooms(request):
    rooms = Room.objects.all()
    return render(request, 'bookings/admin_rooms.html', {'rooms': rooms})


@login_required
@user_passes_test(is_admin)
def add_room(request):
    from .forms import RoomForm
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ruangan berhasil ditambahkan.')
            log_activity(request, 'create', 'Room', room.id, 
                        f"Admin menambahkan ruangan {room.name}")
            return redirect('admin_rooms')
    else:
        form = RoomForm()
    facilities = Facility.objects.all()
    return render(request, 'bookings/add_room.html', {'form': form, 'facilities': facilities})


@login_required
@user_passes_test(is_admin)
def edit_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    from .forms import RoomForm
    if request.method == 'POST':
        form = RoomForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ruangan berhasil diperbarui.')
            log_activity(request, 'update', 'Room', room.id, 
                        f"Admin mengedit ruangan {room.name}")
            return redirect('admin_rooms')
    else:
        form = RoomForm(instance=room)
    facilities = Facility.objects.all()
    return render(request, 'bookings/edit_room.html', {'form': form, 'facilities': facilities, 'room': room})


@login_required
@user_passes_test(is_admin)
def delete_room(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    room.delete()
    messages.info(request, 'Ruangan dihapus.')
    log_activity(request, 'delete', 'Room', room_id, 
                f"Admin menghapus ruangan")
    return redirect('admin_rooms')


@login_required
@user_passes_test(is_admin)
def admin_bookings(request):
    sort = request.GET.get('sort', '-booking_date')
    order = request.GET.get('order', 'desc')
    
    allowed_sorts = ['booking_date', 'room__name', 'user__username', 'status', 'start_time']
    if sort.lstrip('-') not in [s.lstrip('-') for s in allowed_sorts]:
        sort = '-booking_date'
    
    if order == 'asc' and not sort.startswith('-'):
        sort = sort
    elif order == 'desc' and not sort.startswith('-'):
        sort = f'-{sort}'
    
    bookings = Booking.objects.all().order_by(sort)
    
    # Batas waktu untuk label "New" (5 menit terakhir)
    #new_threshold = timezone.now() - timedelta(minutes=5)
    # Ubah menjadi (untuk testing):
    new_threshold = timezone.now() - timedelta(hours=1)  # 1 jam muncul new

    # Auto-mark no-show: booking yang sudah lewat & belum check-in
    now = timezone.now()
    expired_bookings = Booking.objects.filter(
        status='confirmed',
        booking_date__lt=now.date(),
        checked_in_at__isnull=True
    ) | Booking.objects.filter(
        status='confirmed',
        booking_date=now.date(),
        end_time__lt=now.time(),
        checked_in_at__isnull=True
    )
    
    for b in expired_bookings:
        b.status = 'no_show'
        b.save()
        log_activity(request, 'system', 'Booking', b.id, 
                    f"Otomatis no-show: {b.room.name} oleh {b.user.username}")
    # ===== SAMPAI SINI =====

    # Auto check-out & no-show yang lebih lengkap
    now = timezone.now()

    # 1. Auto check-out: sudah check-in tapi belum check-out & waktu sudah lewat
    auto_checkout = Booking.objects.filter(
        status='confirmed',
        checked_in_at__isnull=False,
        checked_out_at__isnull=True
    ).filter(
        Q(booking_date__lt=now.date()) |
        Q(booking_date=now.date(), end_time__lt=now.time())
    )

    for b in auto_checkout:
        b.checked_out_at = now
        b.save()
        log_activity(request, 'system', 'Booking', b.id, 
                    f"Auto check-out: {b.room.name} oleh {b.user.username}")

    # 2. Auto no-show: belum check-in & waktu sudah lewat
    auto_noshow = Booking.objects.filter(
        status='confirmed',
        checked_in_at__isnull=True,
        checked_out_at__isnull=True
    ).filter(
        Q(booking_date__lt=now.date()) |
        Q(booking_date=now.date(), end_time__lt=now.time())
    )

    for b in auto_noshow:
        b.status = 'no_show'
        b.save()
        log_activity(request, 'system', 'Booking', b.id, 
                    f"Auto no-show: {b.room.name} oleh {b.user.username}")

    # Tandai booking yang sudah expired
    now = timezone.now()
    for b in bookings:
        booking_end = timezone.make_aware(
            datetime.combine(b.booking_date, b.end_time)
        ) if not timezone.is_aware(datetime.combine(b.booking_date, b.end_time)) else datetime.combine(b.booking_date, b.end_time)
        b.is_expired = booking_end < now

    # Auto-reject Pending yang sudah lewat (sebelum render)
    now = timezone.now()
    expired_pending = Booking.objects.filter(
        status='pending'
    ).filter(
        Q(booking_date__lt=now.date()) |
        Q(booking_date=now.date(), end_time__lt=now.time())
    )

    for b in expired_pending:
        b.status = 'rejected'
        b.rejection_reason = 'Otomatis ditolak: Waktu booking sudah terlewat.'
        b.save()
        log_activity(request, 'system', 'Booking', b.id, 
                    f"Auto-reject: {b.room.name} oleh {b.user.username} (waktu terlewat)")

    return render(request, 'bookings/admin_bookings.html', {
        'bookings': bookings,
        'current_sort': sort,
        'current_order': order,
        'new_threshold': new_threshold,
        'today': date.today(),
        'now': datetime.now(),
    })


@login_required
@user_passes_test(is_admin)
def approve_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    booking_datetime = timezone.make_aware(
        datetime.combine(booking.booking_date, booking.end_time)
    )
    
    if booking_datetime < timezone.now():
        messages.error(request, 'Tidak bisa menyetujui booking yang sudah lewat.')
        return redirect('admin_bookings')
    
    booking.status = 'confirmed'
    booking.save()
    
    # Kirim email ke peserta (jika ada)
    if booking.participants:
        participant_list = [p.strip() for p in booking.participants.split(',') if p.strip()]
        if participant_list:
            import threading
            threading.Thread(
                target=send_booking_notification,
                args=(booking, participant_list),
                daemon=True
            ).start()
    
    # Buat notifikasi untuk user yang booking
    current_time = timezone.localtime(timezone.now()).strftime('%d/%m %H:%M')
    create_notification(
        booking.user,
        f'[{current_time}] Booking Anda disetujui: {booking.room.name} ({booking.booking_date.strftime("%d/%m")}, {booking.start_time.strftime("%H:%M")}-{booking.end_time.strftime("%H:%M")})',
        booking
    )
    
    # Kirim WebSocket notifikasi ke user yang booking
    send_websocket_notification(booking.user.id, {
        'unread_count': Notification.objects.filter(user=booking.user, is_read=False).count(),
        'notifications': [{
            'id': booking.id,
            'message': f'Booking Anda disetujui: {booking.room.name}',
            'created_at': timezone.localtime(booking.created_at).strftime('%d/%m %H:%M'),
            'is_read': False
        }]
    })
    
    messages.success(request, 'Booking disetujui.')
    return redirect('admin_bookings')
    

@login_required
@user_passes_test(is_admin)
def reject_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    reason = request.POST.get('rejection_reason', '').strip()
    
    # Cek apakah tanggal booking sudah lewat
    booking_datetime = timezone.make_aware(
        datetime.combine(booking.booking_date, booking.end_time)
    )
    
    if booking_datetime < timezone.now():
        messages.error(request, 'Tidak bisa menolak booking yang sudah lewat.')
        return redirect('admin_bookings')
    
    booking.status = 'rejected'
    booking.rejection_reason = reason or None
    booking.save()
    
    # Buat notifikasi untuk user yang booking
    current_time = timezone.localtime(timezone.now()).strftime('%d/%m %H:%M')
    create_notification(
        booking.user,
        f'[{current_time}] Booking Anda ditolak: {booking.room.name} ({booking.booking_date.strftime("%d/%m")}, {booking.start_time.strftime("%H:%M")}-{booking.end_time.strftime("%H:%M")})',
        booking
    )
    
    # Kirim WebSocket notifikasi ke user yang booking
    send_websocket_notification(booking.user.id, {
        'unread_count': Notification.objects.filter(user=booking.user, is_read=False).count(),
        'notifications': [{
            'id': booking.id,
            'message': f'Booking Anda ditolak: {booking.room.name}. Alasan: {reason or "Tidak ada alasan"}',
            'created_at': timezone.localtime(booking.created_at).strftime('%d/%m %H:%M'),
            'is_read': False
        }]
    })
    
    messages.info(request, 'Booking ditolak.')
    log_activity(request, 'reject', 'Booking', booking.id, 
                 f"Admin menolak booking {booking.room.name} oleh {booking.user.username}. Alasan: {reason}")
    return redirect('admin_bookings')
    

@login_required
@user_passes_test(is_admin)
def admin_facilities(request):
    facilities = Facility.objects.all()
    return render(request, 'bookings/admin_facilities.html', {'facilities': facilities})


@login_required
@user_passes_test(is_admin)
def add_facility(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name and not Facility.objects.filter(name=name).exists():
            Facility.objects.create(name=name)
            messages.success(request, 'Fasilitas ditambahkan.')
            log_activity(request, 'create', 'Facility', facility.id, 
                        f"Admin menambahkan fasilitas {facility.name}")
        else:
            messages.error(request, 'Nama tidak valid atau sudah ada.')
    return redirect('admin_facilities')


@login_required
@user_passes_test(is_admin)
def delete_facility(request, facility_id):
    facility = get_object_or_404(Facility, id=facility_id)
    facility.delete()
    messages.info(request, 'Fasilitas dihapus.')
    log_activity(request, 'delete', 'Facility', facility_id, 
                f"Admin menghapus fasilitas")
    return redirect('admin_facilities')


@login_required
@user_passes_test(is_admin)
def admin_settings(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'approval_mode':
            # Simpan Mode Persetujuan
            mode = request.POST.get('approval_mode', 'off')
            if 'approval_mode' in request.POST:
                Setting.objects.update_or_create(key='approval_mode', defaults={'value': 'on'})
            else:
                Setting.objects.update_or_create(key='approval_mode', defaults={'value': 'off'})
            messages.success(request, 'Mode persetujuan disimpan.')
            return redirect('admin_settings')

        elif action == 'working_hours_mode':
            # Simpan Mode Jam Kerja
            if 'working_hours_mode' in request.POST:
                Setting.objects.update_or_create(key='working_hours_mode', defaults={'value': 'working'})
            else:
                Setting.objects.update_or_create(key='working_hours_mode', defaults={'value': 'free'})

            work_start = request.POST.get('work_start', '08:00')
            work_end = request.POST.get('work_end', '17:00')
            work_days = ','.join(request.POST.getlist('work_days')) or '0,1,2,3,4'

            Setting.objects.update_or_create(key='work_start', defaults={'value': work_start})
            Setting.objects.update_or_create(key='work_end', defaults={'value': work_end})
            Setting.objects.update_or_create(key='work_days', defaults={'value': work_days})

            messages.success(request, 'Pengaturan jam kerja disimpan.')
            return redirect('admin_settings')

        # ---------- TAMBAHKAN DUA BLOK INI ----------
        elif action == 'upload_logo':
            # Upload logo perusahaan
            if 'company_logo' in request.FILES:
                logo_file = request.FILES['company_logo']
                if logo_file.content_type in ['image/png', 'image/jpeg', 'image/jpg', 'image/webp']:
                    import os
                    from django.core.files.storage import default_storage

                    # Hapus logo lama jika ada
                    old_logo = Setting.objects.filter(key='company_logo').first()
                    if old_logo and old_logo.value:
                        old_path = os.path.join(settings.MEDIA_ROOT, 'logo', old_logo.value)
                        if os.path.exists(old_path):
                            os.remove(old_path)

                    # Simpan logo baru
                    filename = f"logo_{int(timezone.now().timestamp())}.{logo_file.name.split('.')[-1]}"
                    filepath = default_storage.save(f'logo/{filename}', logo_file)

                    Setting.objects.update_or_create(key='company_logo', defaults={'value': filename})
                    messages.success(request, 'Logo perusahaan berhasil diupload.')
                else:
                    messages.error(request, 'Format file tidak didukung. Gunakan PNG, JPG, atau WEBP.')
            else:
                messages.error(request, 'Tidak ada file yang dipilih.')
            return redirect('admin_settings')

        elif action == 'delete_logo':
            # Hapus logo
            logo = Setting.objects.filter(key='company_logo').first()
            if logo and logo.value:
                import os
                logo_path = os.path.join(settings.MEDIA_ROOT, 'logo', logo.value)
                if os.path.exists(logo_path):
                    os.remove(logo_path)
                logo.delete()
                messages.success(request, 'Logo perusahaan berhasil dihapus.')
            return redirect('admin_settings')
        # ---------- SAMPAI SINI ----------

    # ---------- GET REQUEST ----------
    approval_mode = get_approval_mode()
    working_hours_mode = Setting.objects.filter(key='working_hours_mode').first()
    working_hours_mode = working_hours_mode.value if working_hours_mode else 'free'

    work_start = Setting.objects.filter(key='work_start').first()
    work_start = work_start.value if work_start else '08:00'

    work_end = Setting.objects.filter(key='work_end').first()
    work_end = work_end.value if work_end else '17:00'

    work_days = Setting.objects.filter(key='work_days').first()
    work_days = work_days.value if work_days else '0,1,2,3,4'
    work_days_list = work_days.split(',')

    # ---------- Ambil logo perusahaan ----------
    company_logo = Setting.objects.filter(key='company_logo').first()
    logo_url = None
    if company_logo and company_logo.value:
        logo_url = f'/media/logo/{company_logo.value}'
    # -------------------------------------------

    day_choices = [
        ('0', 'Senin'), ('1', 'Selasa'), ('2', 'Rabu'),
        ('3', 'Kamis'), ('4', 'Jumat'), ('5', 'Sabtu'), ('6', 'Minggu')
    ]

    return render(request, 'bookings/admin_settings.html', {
        'approval_mode': approval_mode,
        'working_hours_mode': working_hours_mode,
        'work_start': work_start,
        'work_end': work_end,
        'work_days': work_days_list,
        'day_choices': day_choices,
        'logo_url': logo_url,   # <-- tambahkan ini
    })
    
    
@login_required
@user_passes_test(is_admin)
def company_identity(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'upload_logo':
            # Simpan nama perusahaan
            company_name = request.POST.get('company_name', '').strip()
            if company_name:
                Setting.objects.update_or_create(key='company_name', defaults={'value': company_name})
            
            # Upload logo
            if 'company_logo' in request.FILES:
                logo_file = request.FILES['company_logo']
                if logo_file.content_type in ['image/png', 'image/jpeg', 'image/jpg', 'image/webp']:
                    import os
                    from django.core.files.storage import default_storage
                    
                    old_logo = Setting.objects.filter(key='company_logo').first()
                    if old_logo and old_logo.value:
                        old_path = os.path.join(settings.MEDIA_ROOT, 'logo', old_logo.value)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    filename = f"logo_{int(timezone.now().timestamp())}.{logo_file.name.split('.')[-1]}"
                    filepath = default_storage.save(f'logo/{filename}', logo_file)
                    
                    Setting.objects.update_or_create(key='company_logo', defaults={'value': filename})
                    messages.success(request, 'Logo perusahaan berhasil diupload.')
                else:
                    messages.error(request, 'Format file tidak didukung. Gunakan PNG, JPG, atau WEBP.')
            else:
                # Hanya update nama tanpa upload logo baru
                if company_name:
                    messages.success(request, 'Nama perusahaan berhasil disimpan.')
            return redirect('company_identity')
        
        elif action == 'delete_logo':
            logo = Setting.objects.filter(key='company_logo').first()
            if logo and logo.value:
                import os
                logo_path = os.path.join(settings.MEDIA_ROOT, 'logo', logo.value)
                if os.path.exists(logo_path):
                    os.remove(logo_path)
                logo.delete()
                messages.success(request, 'Logo perusahaan berhasil dihapus.')
            return redirect('company_identity')
        
        elif action == 'save_name':
            company_name = request.POST.get('company_name', '').strip()
            if company_name:
                Setting.objects.update_or_create(key='company_name', defaults={'value': company_name})
                messages.success(request, 'Nama perusahaan berhasil disimpan.')
            return redirect('company_identity')
    
    # GET request
    company_logo = Setting.objects.filter(key='company_logo').first()
    logo_url = None
    if company_logo and company_logo.value:
        logo_url = f'/media/logo/{company_logo.value}'
    
    company_name = Setting.objects.filter(key='company_name').first()
    company_name = company_name.value if company_name else ''
    
    return render(request, 'bookings/company_identity.html', {
        'logo_url': logo_url,
        'company_name': company_name,
    })


@login_required
@user_passes_test(is_admin)
def dashboard(request):
    today = date.today()
    now = timezone.now()
    
    # Statistik dasar
    bookings_today = Booking.objects.filter(booking_date=today).count()
    first_day = today.replace(day=1)
    bookings_month = Booking.objects.filter(booking_date__gte=first_day).count()
    total_rooms = Room.objects.count()
    total_users = User.objects.count()
    
    # Ruangan terpopuler
    popular_rooms = Room.objects.annotate(total=Count('bookings')).order_by('-total')[:5]
    
    # 7 hari terakhir
    last_7_days = []
    bookings_per_day = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        last_7_days.append(day.strftime('%d-%m-%Y'))
        count = Booking.objects.filter(booking_date=day, status='confirmed').count()
        bookings_per_day.append(count)
    
    # ===== STATISTIK LANJUTAN =====
    
    # 1. Utilisasi per jam (hari ini)
    hourly_labels = []
    hourly_data = []
    for hour in range(7, 20):  # jam 07:00 - 19:00
        hourly_labels.append(f'{hour:02d}:00')
        count = Booking.objects.filter(
            booking_date=today,
            status='confirmed',
            start_time__hour__lte=hour,
            end_time__hour__gte=hour
        ).count()
        hourly_data.append(count)
    
    # 2. Peak hours (hari ini) - jam dengan booking terbanyak
    peak_hour = hourly_labels[hourly_data.index(max(hourly_data))] if max(hourly_data) > 0 else '-'
    peak_count = max(hourly_data)
    
    # 3. Room utilization rate (bulan ini)
    total_bookings_month = Booking.objects.filter(booking_date__gte=first_day, status='confirmed').count()
    # Asumsi: setiap ruangan bisa dipakai 8 slot per hari (08:00-17:00, per jam)
    working_days = (today - first_day).days + 1
    max_possible_bookings = total_rooms * working_days * 8
    utilization_rate = round((total_bookings_month / max_possible_bookings * 100), 1) if max_possible_bookings > 0 else 0
    
    # 4. User paling sering booking (bulan ini)
    top_users = User.objects.annotate(
        total=Count('bookings', filter=Q(bookings__booking_date__gte=first_day))
    ).order_by('-total')[:5]
    
    # 5. Status booking bulan ini
    status_labels = ['Confirmed', 'Pending', 'Rejected', 'No Show']
    status_data = [
        Booking.objects.filter(booking_date__gte=first_day, status='confirmed').count(),
        Booking.objects.filter(booking_date__gte=first_day, status='pending').count(),
        Booking.objects.filter(booking_date__gte=first_day, status='rejected').count(),
        Booking.objects.filter(booking_date__gte=first_day, status='no_show').count(),
    ]
    
    return render(request, 'bookings/dashboard.html', {
        'bookings_today': bookings_today,
        'bookings_month': bookings_month,
        'total_rooms': total_rooms,
        'total_users': total_users,
        'popular_rooms': popular_rooms,
        'last_7_days': last_7_days,
        'bookings_per_day': bookings_per_day,
        # Statistik lanjutan
        'hourly_labels': hourly_labels,
        'hourly_data': hourly_data,
        'peak_hour': peak_hour,
        'peak_count': peak_count,
        'utilization_rate': utilization_rate,
        'top_users': top_users,
        'status_labels': status_labels,
        'status_data': status_data,
    })

# ---------- Admin: User Management ----------
@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'bookings/admin_users.html', {'users': users})


@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        is_admin_user = request.POST.get('is_admin') == 'on'

        if not username or not password:
            messages.error(request, 'Username dan password wajib diisi.')
            return redirect('admin_users')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username sudah digunakan.')
            return redirect('admin_users')

        user = User.objects.create(
            username=username,
            email=email,
            is_superuser=is_admin_user,
            is_staff=is_admin_user,
        )
        user.set_password(password)
        user.save()
        messages.success(request, f'User {username} berhasil ditambahkan.')
        log_activity(request, 'create', 'User', user.id, 
             f"Admin menambahkan user {user.username}")
        return redirect('admin_users')

    return render(request, 'bookings/add_user.html')


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        is_admin_user = request.POST.get('is_admin') == 'on'

        if not username:
            messages.error(request, 'Username wajib diisi.')
            return redirect('edit_user', user_id=user_id)

        if User.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, 'Username sudah digunakan.')
            return redirect('edit_user', user_id=user_id)

        user.username = username
        user.email = email
        user.is_superuser = is_admin_user
        user.is_staff = is_admin_user
        user.save()
        messages.success(request, f'User {username} berhasil diperbarui.')
        return redirect('admin_users')

    return render(request, 'bookings/edit_user.html', {'edit_user': user})


@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if user.id == request.user.id:
        messages.error(request, 'Anda tidak bisa menghapus akun sendiri.')
        return redirect('admin_users')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.info(request, f'User {username} berhasil dihapus.')
        log_activity(request, 'delete', 'User', user.id, 
             f"Admin menghapus user {username}")
        return redirect('admin_users')

    return redirect('admin_users')


@login_required
@user_passes_test(is_admin)
def reset_password(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        if len(new_password) < 6:
            messages.error(request, 'Password minimal 6 karakter.')
            return redirect('admin_users')

        user.set_password(new_password)
        user.save()
        messages.success(request, f'Password untuk {user.username} berhasil direset.')
        return redirect('admin_users')

    return redirect('admin_users')

# ---------- Admin: User Management ----------
@login_required
@user_passes_test(is_admin)
def manage_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'bookings/manage_users.html', {'users': users})


@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        is_admin_user = request.POST.get('is_admin') == 'on'

        if not username or not password:
            messages.error(request, 'Username dan password wajib diisi.')
            return redirect('manage_users')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username sudah digunakan.')
            return redirect('manage_users')

        user = User.objects.create(
            username=username,
            email=email,
            is_superuser=is_admin_user,
            is_staff=is_admin_user,
        )
        user.set_password(password)
        user.save()
        messages.success(request, f'User {username} berhasil ditambahkan.')
        log_activity(request, 'create', 'User', user.id, 
             f"Admin menambahkan user {user.username}")
        return redirect('manage_users')

    return redirect('manage_users')


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    edit_user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        is_admin_user = request.POST.get('is_admin') == 'on'

        if not username:
            messages.error(request, 'Username wajib diisi.')
            return redirect('edit_user', user_id=user_id)

        if User.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, 'Username sudah digunakan.')
            return redirect('edit_user', user_id=user_id)

        edit_user.username = username
        edit_user.email = email
        edit_user.is_superuser = is_admin_user
        edit_user.is_staff = is_admin_user
        edit_user.save()
        messages.success(request, f'User {username} berhasil diperbarui.')
        return redirect('manage_users')

    return render(request, 'bookings/edit_user.html', {'edit_user': edit_user})


@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if user.id == request.user.id:
        messages.error(request, 'Anda tidak bisa menghapus akun sendiri.')
        return redirect('manage_users')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.info(request, f'User {username} berhasil dihapus.')
        log_activity(request, 'delete', 'User', user.id, 
             f"Admin menghapus user {username}")
    return redirect('manage_users')


@login_required
@user_passes_test(is_admin)
def reset_password(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        if len(new_password) < 6:
            messages.error(request, 'Password minimal 6 karakter.')
        else:
            user.set_password(new_password)
            user.save()
            messages.success(request, f'Password untuk {user.username} berhasil direset.')
    return redirect('manage_users')

@login_required
@user_passes_test(is_admin)
def audit_log(request):
    logs = AuditLog.objects.all().order_by('-created_at')[:100]
    return render(request, 'bookings/audit_log.html', {'logs': logs})