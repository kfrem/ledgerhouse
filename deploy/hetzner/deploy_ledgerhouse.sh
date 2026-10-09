#!/usr/bin/env bash
# Deploy LedgerHouse from an already-cloned /srv/ledgerhouse checkout.
# Secrets belong only in /srv/ledgerhouse/.env, never in this repository.

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/ledgerhouse}"
COMPOSE=(docker compose --env-file .env -f docker-compose.prod.yml)

cd "$APP_DIR"

if [[ ! -f .env ]]; then
    echo "ERROR: $APP_DIR/.env is required and must contain production-only secrets."
    exit 1
fi

echo "==> Building the production web image"
"${COMPOSE[@]}" build web

echo "==> Starting PostgreSQL and waiting for its health check"
"${COMPOSE[@]}" up -d db

until "${COMPOSE[@]}" exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null; do
    sleep 2
done

echo "==> Applying database migrations as the schema owner"
DB_ADMIN_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER)"
DB_ADMIN_PASSWORD="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_PASSWORD)"
"${COMPOSE[@]}" run --rm \
    -e POSTGRES_USER="$DB_ADMIN_USER" \
    -e POSTGRES_PASSWORD="$DB_ADMIN_PASSWORD" \
    web python manage.py migrate --noinput
unset DB_ADMIN_USER DB_ADMIN_PASSWORD

echo "==> Starting the restricted runtime service"
"${COMPOSE[@]}" up -d web

echo "==> Waiting for LedgerHouse health"
for _attempt in {1..30}; do
    if curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/healthz/ >/dev/null; then
        echo "LedgerHouse is healthy."
        exit 0
    fi
    sleep 2
done

echo "ERROR: LedgerHouse did not become healthy within 60 seconds."
"${COMPOSE[@]}" logs --tail=100 web
exit 1
