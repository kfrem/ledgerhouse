# LedgerHouse Release Hardening and Go-Live Preparation

Date: 2026-08-03

## Scope and conclusion

This pass was confined to the LedgerHouse project folder. It completed the
remaining locally verifiable release hardening and did not alter any other
product, provider account or credential store.

LedgerHouse is ready for a controlled server deployment and public-domain smoke
testing. It is not claimed to be live yet: no server deployment, DNS/TLS
verification, production HMRC call, Companies House live filing, bank consent,
payment collection or customer-data transaction was performed in this pass.

## Changes made

- `accounting/companies_house.py`
  - A gateway acknowledgement now records `Pending`, not success.
  - An unrecognised gateway response now records `Failed`, not success.
- `accounting/tests/test_companies_house.py`
  - Added acknowledgement and unrecognised-response regression coverage.
- `ledgerhouse/settings.py`
  - Enabled `SECURE_HSTS_PRELOAD` when HTTPS security is deliberately enabled.
- `accounting/views.py`, `ledgerhouse/urls.py`, `accounting/tests/test_healthcheck.py`
  - Added unauthenticated `/healthz/` with a database readiness probe. It
    returns only `{"status":"ok"}` or `{"status":"unavailable"}`.
- `docker-compose.prod.yml`
  - Requires a field-encryption key and passes LedgerHouse-owned HMRC and
    Companies House settings into the production web container.
  - Added a production container health check.
- `.env.example`
  - Replaced the other-product HMRC reference with a LedgerHouse-only template
    and listed the non-secret configuration keys required for HMRC, Companies
    House and token encryption.
- `deploy/hetzner/Caddyfile.ledgerhouse`
  - Added the TLS reverse-proxy configuration for `ledgerhouse.finaccord.pro`.
- `deploy/hetzner/deploy_ledgerhouse.sh`
  - Added an idempotent server deployment sequence: build, database health,
    migrate, start the runtime service and verify `/healthz/`.
- `DEPLOYMENT.md`
  - Updated the deployment runbook to use the checked deployment script and
    Caddy configuration.

## Verification performed

| Command or route | Result |
| --- | --- |
| `docker compose exec -T web python manage.py test --noinput --verbosity 1` | PASS: 204 tests in 65.166 seconds. |
| Focused Companies House suite | PASS: 39 tests. |
| Focused health, Companies House and HMRC suites | PASS: 68 tests. |
| `docker compose exec -T web python manage.py makemigrations --check --dry-run` | PASS: no migration changes detected. |
| `docker compose exec -T web python manage.py check` | PASS: no issues. |
| Production-shaped `manage.py check --database default --deploy --fail-level ERROR` | PASS with release-check values. The expected warnings identify the local development superuser and a deliberately non-production dummy test key; neither was accepted as production evidence. |
| `docker compose -f docker-compose.prod.yml config --quiet` | PASS with release-check values. |
| `docker compose exec -T web python manage.py local_production_rehearsal --strict` | PASS: PostgreSQL, migrations, tenant data and report/export outputs verified. |
| `docker compose exec -T web python manage.py local_acceptance_suite --strict` | PASS: client and practice routes, reports, PDF/CSV/ZIP outputs and no-HMRC pack verified. |
| `docker compose exec -T web python manage.py commercial_readiness_rehearsal --strict` | PASS: six synthetic tenants passed accounting, reporting and external-filing-safety checks. |
| `bash -n deploy/hetzner/deploy_ledgerhouse.sh` | PASS. |
| `curl http://127.0.0.1:8000/healthz/` | PASS: HTTP 200, `{"status":"ok"}`. |
| In-app Browser: `http://127.0.0.1:8000/integrations/hmrc/` | PASS: shows LedgerHouse only, declares shared HMRC configuration unavailable and keeps authorisation disabled until LedgerHouse-owned settings are present. |

The in-app Browser client blocked direct navigation to `/healthz/`; the same
route was independently checked through the local HTTP client above. This is a
browser-client restriction, not an application failure.

## Provider safety state

- The previously recorded harmless LedgerHouse HMRC Hello World sandbox call
  remains the only confirmed HMRC API activity in this project evidence.
- No HMRC VAT filing was submitted.
- No Companies House gateway submission was sent in this pass.
- Gateway acknowledgement and unknown responses now fail closed rather than
  creating an accepted or submitted outcome.

## Deployment actions that cannot be performed inside this local project

1. On the selected Hetzner server, provide a production-only `/srv/ledgerhouse/.env`
   with a real secret key, Fernet field-encryption key, database passwords,
   public domain, CSRF origin and only the approved LedgerHouse provider values.
2. Create the restricted PostgreSQL runtime role using
   `deploy/create_app_role.sql`, set `APP_DB_USER` and `APP_DB_PASSWORD`, and
   verify the web container no longer uses a superuser or `BYPASSRLS` role.
3. Point `ledgerhouse.finaccord.pro` to the server, install
   `deploy/hetzner/Caddyfile.ledgerhouse`, validate/reload Caddy, and confirm a
   public HTTPS certificate and `/healthz/` response.
4. Run `deploy/hetzner/deploy_ledgerhouse.sh` on the server, then repeat the
   public-domain smoke, accessibility and security scans against the final URL.
5. Configure and exercise only the separately-approved LedgerHouse HMRC and
   Companies House transports in their intended environments. Do not reuse
   another product's client ID, secret, package reference or activity history.

## Commits

None. The LedgerHouse worktree already contains a large amount of uncommitted
work outside this pass, so changes were not staged or committed automatically.
