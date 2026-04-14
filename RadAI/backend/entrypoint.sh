#!/bin/sh
# RadAI backend entrypoint.
# Runs schema migrations and seeds the default admin user before handing
# off to the real command. Safe for both the API (`uvicorn ...`) and the
# Celery worker — migrations only run when the primary process is uvicorn
# so workers don't race with the API on schema changes.
set -e

if [ "$1" = "uvicorn" ]; then
    echo "[entrypoint] Applying database migrations..."
    alembic upgrade head

    echo "[entrypoint] Seeding default admin user..."
    if ! python3 /app/scripts/seed_admin.py; then
        echo "[entrypoint] WARNING: seed_admin.py failed; continuing startup." >&2
    fi
fi

exec "$@"
