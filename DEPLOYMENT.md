# LedgerHouse Deployment Guide

## Requirements

- Docker Engine + Docker Compose v2
- PostgreSQL 16 (bundled in the compose stack). **PostgreSQL is mandatory** —
  the double-entry balance constraint, closed-period and VAT-lock triggers,
  audit-log immutability and multi-tenant RLS are enforced by PostgreSQL
  triggers/policies and do not exist on any other backend. The settings module
  has no SQLite fallback and `manage.py check --database default` fails on a
  non-PostgreSQL connection (`accounting.E001`).

## Configuration

All configuration is environment-driven. Copy `.env.example` to `.env` and set:

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | Yes (prod) | App refuses to start with `DEBUG=False` and no key |
| `DEBUG` | Yes | Must be `False` in production |
| `ALLOWED_HOSTS` | Yes | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | If serving over HTTPS | e.g. `https://ledger.example.com` |
| `SECURE_TLS` | Once HTTPS is terminated | Enables SSL redirect, secure cookies, HSTS |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Yes | Admin/owner credentials (used for migrations) |
| `APP_DB_USER` / `APP_DB_PASSWORD` | Recommended | Restricted runtime role, see below |

Never commit `.env`.

## First deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
# optional demo data:
docker compose -f docker-compose.prod.yml run --rm web python manage.py seed_db
```

## Restricted database role (strongly recommended)

By default the app connects with the admin credentials, which in the bundled
Postgres image is a **superuser** — superusers bypass row-level security, so
tenant isolation then rests solely on the middleware issuing
`SET ROLE ledger_tenant_role`. To make RLS the default posture:

1. Edit the password in `deploy/create_app_role.sql`, then run it as admin:
   ```bash
   docker exec -i ledgerhouse_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < deploy/create_app_role.sql
   ```
2. Set `APP_DB_USER=ledgerhouse_app` and `APP_DB_PASSWORD=...` in `.env`.
3. Restart: `docker compose -f docker-compose.prod.yml up -d web`

Migrations must always run as the admin/owner role (trigger and policy DDL),
e.g. `docker compose -f docker-compose.prod.yml run --rm -e POSTGRES_USER=$POSTGRES_USER -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD web python manage.py migrate`.

The system check `accounting.W001` warns at startup if the runtime connection
is still a superuser/BYPASSRLS role while `DEBUG=False`.

## Upgrades

```bash
git pull
docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml run --rm -e POSTGRES_USER=$POSTGRES_USER -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD web python manage.py migrate
docker compose -f docker-compose.prod.yml up -d web
```

The web container start command runs `collectstatic` and
`manage.py check --database default --deploy --fail-level ERROR` before
starting gunicorn, so misconfiguration fails fast instead of serving.

## Verification suite

```bash
docker compose up -d                       # dev stack
docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest         # must be 100% green
```

The suite refuses to run on a non-PostgreSQL backend (see `conftest.py`).

## Operational notes

- **Backups:** the ledger lives in the `postgres_data` volume; schedule
  `pg_dump` (e.g. `docker exec ledgerhouse_db pg_dump -U $POSTGRES_USER $POSTGRES_DB`)
  and test restores. Evidence documents are currently stored in-database, so
  DB backups cover them too.
- **TLS:** run a reverse proxy (Caddy/nginx/Traefik) in front of port 8000 and
  set `SECURE_TLS=True` + `CSRF_TRUSTED_ORIGINS`.
- **Known roadmap items** (documented in the Stage 6 audit, not blockers):
  external object storage for evidence documents, one-to-many bank payment
  matching with write-off thresholds, and multi-currency support (system is
  GBP-only by design in this phase).
