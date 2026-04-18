#!/bin/sh
set -e

# Default to empty string — matches settings.py's documented "unset = full stack" behavior.
# The gunicorn branch is reached when DJANGO_MODE is empty, "api", "ui", or any
# unrecognised value; explicit "worker" and "beat" branches are checked first.
DJANGO_MODE="${DJANGO_MODE:-}"

echo "Running migrations..."
python manage.py migrate --noinput

# Celery worker mode — reads from EFS write-cache and uploads to backends
if [ "$DJANGO_MODE" = "worker" ]; then
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
  echo "Starting Celery worker..."
  exec celery -A config worker \
      --loglevel=info \
      --concurrency="${CELERY_WORKERS:-4}"
fi

# Celery beat mode — fires scheduled tasks (OAuth token refresh, etc.)
if [ "$DJANGO_MODE" = "beat" ]; then
  echo "Starting Celery beat..."
  exec celery -A config beat --loglevel=info
fi

# Default: gunicorn (handles both DJANGO_MODE=api, DJANGO_MODE=ui, or unset)
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
