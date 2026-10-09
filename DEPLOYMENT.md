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

## HMRC service approvals

HMRC access is service-specific. LedgerHouse records VAT MTD and Income Tax MTD
as REST/OAuth services, while Corporation Tax Online, PAYE Online/RTI, CIS
Online and Self Assessment Online use separate XML Gateway routes. Do not reuse
one service's approval state as proof that another service is approved.

The `/integrations/hmrc/services/` workspace stores each client's tax
references and filing payloads in encrypted fields. Live filing must remain
disabled until the exact service has passed its official HMRC testing route,
production credentials have been verified, the client has authorised the
filing, and release management has explicitly enabled that service. The current
multi-service transport is intentionally locked and fails closed.

For Income Tax MTD, configure the subscriptions displayed at
`/integrations/hmrc/services/`, add `read:self-assessment` and
`write:self-assessment` to the OAuth scopes, and complete sandbox endpoint and
fraud-header testing before requesting production access. Check the current
HMRC application window before making any production claim.

For XML services, keep `HMRC_XML_TRANSPORT_ENABLED=False` until HMRC has issued
the XML Vendor ID and test credentials and the current CT600, RTI, CIS and Self
Assessment bodies have passed the relevant LTS/ETS schemas, business rules and
recognition scenarios. A working generic envelope is not evidence that a
service-specific return body has been accepted by HMRC.

## Companies House live filing

Companies House presenter credentials and the LedgerHouse live package reference
belong only in `.secrets/companies_house_ledgerhouse_live.env`, never in source
control or a report. Before deployment, copy that file to the server's private
LedgerHouse directory, apply `chmod 600`, and set `LEDGERHOUSE_SECRETS_DIR` in
the server `.env` to that directory. The production Compose stack mounts it
read-only.

Set `COMPANIES_HOUSE_FILING_TEST_FLAG=0` and
`COMPANIES_HOUSE_LIVE_APPROVAL_CONFIRMED=True` only after written approval.
Keep `COMPANIES_HOUSE_FILING_LIVE_ENABLED=False` and
`COMPANIES_HOUSE_FILING_SEND_ENABLED=False` until the release manager has
completed the deployment checks and has an authorised client filing to make.
The test presenter account and package reference remain separate and must never
be used in this production configuration.

## First deploy

```bash
chmod +x deploy/hetzner/deploy_ledgerhouse.sh
deploy/hetzner/deploy_ledgerhouse.sh
```

The script starts PostgreSQL, waits for it, applies migrations, starts the web
service and verifies `/healthz/`. Before running it, copy
`deploy/hetzner/Caddyfile.ledgerhouse` to `/etc/caddy/Caddyfile`, validate it
with `caddy validate --config /etc/caddy/Caddyfile`, then reload Caddy. Do this
only after `ledgerhouse1.finaccord.pro` resolves to the server.

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

The container health check calls `http://127.0.0.1:8000/healthz/`. It returns
only `{"status":"ok"}` after a database `SELECT 1`, or HTTP 503 with a generic
unavailable status. It exposes no account, provider or credential information.

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
- **Health probe:** install `deploy/hetzner/ledgerhouse-healthcheck.sh`,
  `.service` and `.timer` on the host. The timer records local application
  failures in the system journal every five minutes. It is intentionally not
  an external alert service; configure a monitored alert destination before
  accepting production client data.
- **TLS:** run a reverse proxy (Caddy/nginx/Traefik) in front of port 8000 and
  set `SECURE_TLS=True` + `CSRF_TRUSTED_ORIGINS`.
- **Known roadmap items** (documented in the Stage 6 audit, not blockers):
  external object storage for evidence documents, one-to-many bank payment
  matching with write-off thresholds, and multi-currency support (system is
  GBP-only by design in this phase).
