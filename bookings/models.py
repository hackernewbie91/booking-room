from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class Facility(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name_plural = "Facilities"
        ordering = ['name']

    def __str__(self):
        return self.name


class Room(models.Model):
    name = models.CharField(max_length=120)
    capacity = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='rooms/', null=True, blank=True)
    facilities = models.ManyToManyField(Facility, blank=True, related_name='rooms')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class RecurringPattern(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Harian'),
        ('weekly', 'Mingguan'),
        ('biweekly', '2 Mingguan'),
        ('monthly', 'Bulanan'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recurring_patterns')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='recurring_patterns')
    start_time = models.TimeField()
    end_time = models.TimeField()
    start_date = models.DateField()
    end_date = models.DateField()
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    interval = models.IntegerField(default=1)
    days_of_week = models.CharField(max_length=30, blank=True, help_text="Contoh: 0,2,4 (Senin=0, Minggu=6)")
    purpose = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Active'), ('stopped', 'Stopped')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.room.name} ({self.frequency})"


class Booking(models.Model):
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
        ('no_show', 'No Show'),
        
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    purpose = models.TextField(blank=True, default='')
    participants = models.TextField(blank=True, default='')  # <-- TAMBAHKAN INI
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    rejection_reason = models.TextField(null=True, blank=True)
    recurring_pattern = models.ForeignKey(RecurringPattern, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')
    created_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    is_no_show = models.BooleanField(default=False)

    class Meta:
        ordering = ['-booking_date', '-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.room.name} ({self.booking_date})"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notif for {self.user.username}: {self.message[:50]}"
        

class RoomReview(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Review {self.room.name} - {self.rating}★ by {self.user.username}"


class WaitingList(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='waiting_list')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='waiting_list')
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    purpose = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, default='waiting', choices=[
        ('waiting', 'Waiting'),
        ('notified', 'Notified'),
        ('converted', 'Converted to Booking'),
        ('expired', 'Expired'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        unique_together = ['room', 'booking_date', 'start_time', 'end_time', 'user']
    
    def __str__(self):
        return f"{self.user.username} waiting for {self.room.name} on {self.booking_date} ({self.start_time}-{self.end_time})"


class Setting(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.key} = {self.value}"
    

class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=50, blank=True)
    object_id = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.user} - {self.action}"