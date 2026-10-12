#!/usr/bin/env sh
set -eu

if [ -z "${DATABASE_URL:-}" ] && {
    [ -z "${POSTGRES_USER:-}" ] ||
    [ -z "${POSTGRES_PASSWORD:-}" ] ||
    [ -z "${POSTGRES_HOST:-}" ] ||
    [ -z "${POSTGRES_PORT:-}" ] ||
    [ -z "${POSTGRES_DB:-}" ];
}; then
    echo "Set DATABASE_URL or all POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_HOST/POSTGRES_PORT/POSTGRES_DB variables." >&2
    exit 2
fi

exec alembic upgrade head

