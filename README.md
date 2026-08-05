// Install & configure Redis
sudo apt update
sudo apt install redis-server -y

Note : Gunakan redis 8.10 atau lebih tinggi

sudo nano /etc/redis/redis.conf
cari requirepass : # requirepass Linuxer91

// Konfigurasi Django untuk Redis
Di settings.py, pastikan CHANNEL_LAYERS sudah diatur untuk Redis tanpa password/dengan password

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [{
                'address': 'redis://127.0.0.1:6379/0',
                'password': 'strongpassword',
            }],
        },
    },
}


// Buat database
sudo -u postgres psql -c "CREATE USER appuser WITH PASSWORD 'dejavu91';"
sudo -u postgres psql -c "CREATE DATABASE room_booking_django OWNER appuser;"
sudo -u postgres psql -c "ALTER USER appuser CREATEDB;"

//Buat directory project Apps
/opt/roombooking

// buat venv
cd /opt/roombooking/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

// Jalankan Migrasi (membuat tabel)
source venv/bin/activate
python manage.py migrate

// Buat superuser
source venv/bin/activate
python manage.py createsuperuser

// jalankan update_css.sh
./update_css.sh

// Setup systemd untuk production
sudo nano /etc/systemd/system/roombooking.service

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
