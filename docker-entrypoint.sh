#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Checking Redis connectivity..."
python - <<'EOF'
import os, sys
url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
try:
    import redis
    redis.from_url(url).ping()
    print("Redis OK")
except Exception as exc:
    print(f"Warning: Redis not reachable ({exc}); async uploads will fail until it is available.", file=sys.stderr)
EOF

echo "Recovering pending uploads..."
python manage.py recover_pending_uploads || echo "Warning: recover_pending_uploads failed; continuing startup." >&2

echo "Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-30}" \
    --access-logfile - \
    --error-logfile -
