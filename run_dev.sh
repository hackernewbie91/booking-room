#!/usr/bin/env bash

sudo fuser -k 8880/tcp
# Aktifkan virtual environment
source venv/bin/activate

export DJANGO_ALLOW_ASYNC_UNSAFE=true
# Jalankan Django development server
daphne -b 127.0.0.1 -p 8880 roombooking.asgi:application
