# Stage 1: TypeScript build
FROM node:20-slim AS node-build
WORKDIR /app
COPY fileproxy/package.json fileproxy/package-lock.json* ./
RUN npm ci
COPY fileproxy/static/ts ./static/ts
COPY fileproxy/tsconfig*.json ./
RUN npm run ts:build

# Stage 2: Python app
FROM python:3.13-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install --no-cache-dir poetry

WORKDIR /app

COPY fileproxy/pyproject.toml fileproxy/poetry.lock* ./
RUN poetry install --without dev --no-root

# uvicorn is installed via pip (not poetry) to avoid a lock-file update cycle.
# When the dev environment has network access, add it properly with:
#   cd fileproxy && poetry add "uvicorn[standard]>=0.32,<1.0"
RUN pip install --no-cache-dir "uvicorn[standard]>=0.32,<1.0"

COPY fileproxy/ ./

# Copy compiled JS from node stage
COPY --from=node-build /app/static/js ./static/js

# collectstatic — dummy vault key satisfies required=True + expected_len=32
RUN FILEPROXY_VAULT_MASTER_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
    DJANGO_SECRET_KEY=build-only-not-used-in-production \
    python manage.py collectstatic --noinput

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
