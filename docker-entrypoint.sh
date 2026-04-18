#!/bin/sh
set -e

# Shared startup checks run by both the Celery worker and Gunicorn branches.
# Warns (does not abort) on Redis failure so the process can still start and
# surface a cleaner error later rather than a cryptic container restart loop.
prepare_app() {
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
}

echo "Running migrations..."
python manage.py migrate --noinput

# Celery worker mode — reads from EFS write-cache and uploads to backends
if [ "$DJANGO_MODE" = "worker" ]; then
  prepare_app
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

# Default: gunicorn with UvicornWorker (ASGI) for DJANGO_MODE=api, ui, or unset.
# The UvicornWorker runs an asyncio event loop per worker process, allowing
# async streaming responses to multiplex many concurrent file transfers without
# blocking the process while waiting for network I/O between chunks.
prepare_app
echo "Starting gunicorn (UvicornWorker / ASGI)..."
exec gunicorn config.asgi:application \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-30}" \
    --access-logfile - \
    --error-logfile -
