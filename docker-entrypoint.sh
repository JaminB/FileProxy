#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Recovering pending uploads..."
python manage.py recover_pending_uploads

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-30}" \
    --access-logfile - \
    --error-logfile -
