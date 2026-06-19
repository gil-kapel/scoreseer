#!/bin/sh
# Apply migrations, then hand off to the container CMD (the app server).
set -e
cd /app/backend
echo "[entrypoint] applying migrations..."
alembic upgrade head
echo "[entrypoint] starting: $*"
exec "$@"
