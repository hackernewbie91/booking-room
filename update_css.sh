#!/usr/bin/env bash

cd /opt/roombooking
source venv/bin/activate
python manage.py collectstatic --noinput
