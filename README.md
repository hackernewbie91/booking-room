**Daftar Isi**
1. Persyaratan Server
2. Install Dependencies
3. Setup PostgreSQL
4. Setup Redis altest version
5. Clone Repository dari GitHub
6. Setup Virtual Environment
7. Konfigurasi .env
8. Jalankan Migrasi
9. Buat Superuser
10. Kumpulkan Static Files
11. Setup Daphne Service
12. Konfigurasi Domain & SSL
13. Verifikasi Aplikasi
14. Troubleshooting

**1. Persyaratan Server**
Komponen	Minimal
OS	Ubuntu 22.04 / 24.04 LTS
RAM	2 GB
CPU	1 core
Python	3.10+
PostgreSQL	14+
Redis	6+
Git	Terbaru

**2. Install Dependencies**
```ini
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    redis-server git curl
```
**3. Setup PostgreSQL**
```ini
sudo -u postgres psql

CREATE USER appuser WITH PASSWORD 'password_anda';
CREATE DATABASE room_booking_django OWNER appuser;
ALTER USER appuser CREATEDB;
\q
```
**4. Setup Redis**
```ini
sudo nano /etc/redis/redis.conf
```
Ubah supervised no menjadi supervised systemd.
Simpan, lalu:

```ini
sudo systemctl restart redis-server
sudo systemctl enable redis-server
redis-cli ping   # harus PONG
```
**5. Clone Repository dari GitHub**
```ini
cd /opt
git clone https://github.com/hackernewbie91/booking-room.git roombooking
cd /opt/roombooking
```
**6. Setup Virtual Environment**
```ini
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
**7. Konfigurasi .env**
```ini
nano .env
```
Isi:

```ini
SECRET_KEY=generate-random-string-panjang
DEBUG=False
ALLOWED_HOSTS=domain-anda.com,localhost,127.0.0.1
DATABASE_URL=postgres://appuser:password_anda@localhost:5432/room_booking_django

EMAIL_HOST=mail.domain-anda.com
EMAIL_PORT=465
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
EMAIL_HOST_USER=noreply@domain-anda.com
EMAIL_HOST_PASSWORD=password_email_anda
DEFAULT_FROM_EMAIL=RoomBooking <noreply@domain-anda.com>
```
**8. Jalankan Migrasi**
```ini
python3 manage.py makemigrations bookings
python3 manage.py migrate
```
**9. Buat Superuser**
```ini
python3 manage.py createsuperuser
```
**10. Kumpulkan Static Files**
```ini
python3 manage.py collectstatic --noinput
```
**11. Setup Daphne Service**
```ini
sudo nano /etc/systemd/system/roombooking.service
```
```ini
[Unit]
Description=RoomBooking Django Application (Daphne)
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/roombooking
EnvironmentFile=/opt/roombooking/.env
ExecStart=/opt/roombooking/venv/bin/daphne -b 0.0.0.0 -p 8880 roombooking.asgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Aktifkan:

```ini
sudo systemctl daemon-reload
sudo systemctl enable roombooking
sudo systemctl start roombooking
sudo systemctl status roombooking
```
**12. Konfigurasi Domain & SSL**
Menggunakan Cloudflare Tunnel
```ini
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

cloudflared tunnel login
cloudflared tunnel create roombooking
Buat ~/.cloudflared/config.yml:

yaml
tunnel: <TUNNEL-ID>
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: room.domain-anda.com
    service: http://localhost:8880
  - service: http_status:404
```
Jalankan:

```ini
cloudflared tunnel run roombooking
```
Atau sebagai service:

```ini
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```
**13. Verifikasi Aplikasi**
Buka https://room.domain-anda.com

Login dengan superuser.

Buat ruangan, fasilitas, user.

Cek notifikasi, check-in/out, approval mode, dll.

**14. Troubleshooting**
Masalah	Solusi
Service tidak jalan	sudo journalctl -u roombooking -f
Static files tidak muncul	python3 manage.py collectstatic --noinput lalu restart service
Database connection error	Cek DATABASE_URL di .env, tes psql
WebSocket tidak berfungsi	Cek Redis redis-cli ping, cek Daphne service
**
🎉 Selesai! RoomBooking Enterprise siap digunakan di server baru.**
