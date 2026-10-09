# LedgerHouse Hetzner Deployment Verification

**Date:** 24 August 2026  
**Target:** `https://ledgerhouse1.finaccord.pro`  
**Server:** `ledgerhouse-prod`  
**Scope:** Deploy the locally verified LedgerHouse source, apply migrations,
and prove the application on the existing Hetzner production stack. No HMRC or
Companies House filing was submitted.

## Result

LedgerHouse is deployed on Hetzner and serving the current application build
through Caddy, Gunicorn and PostgreSQL. The public health endpoint returns HTTP
200, the web and database containers are healthy, all migrations through
`0036` are applied, and the full server-side regression suite passes.

## Safety and rollback evidence

- A PostgreSQL custom-format dump was created before deployment.
- A compressed copy of the previously deployed application was created.
- The server environment file was backed up without displaying its contents.
- Backup directory:
  `/srv/ledgerhouse/backups/deploy-20260824T222033Z`
- The backup directory is mode `700`; backup files are mode `600`.
- The release archive excluded `.env`, `.secrets`, Git metadata, local output,
  temporary files, cached bytecode and previous backups.
- Release archive SHA-256:
  `D5ECC1A3B1B7163660FD84797593A6D1EF6648DF33AEBAD1A71EB93BC18FF3BA`
- Temporary release files were removed after successful verification.

## Deployment corrections

### Migration ownership

The first deployment attempt stopped before replacing the live web service.
The deployment script was using the restricted runtime database account for
schema migrations, which PostgreSQL correctly rejected.

`deploy/hetzner/deploy_ledgerhouse.sh` was corrected to obtain the database
owner credentials from the protected database container for the migration
process only. The credentials are unset immediately afterwards. The web
service continues to run as the restricted application role.

### Empty HMRC endpoint variables

The first complete Hetzner regression found four OAuth errors because blank
production environment variables overrode the application's safe HMRC sandbox
endpoint defaults.

`ledgerhouse/settings.py` now treats blank endpoint values as unset, and
`docker-compose.prod.yml` supplies explicit HMRC sandbox API, authorization and
token endpoint defaults. This was reproduced with blank variables and retested.

## Commands and results

1. Local system check: passed with no issues.
2. Local migration drift check: no changes detected.
3. Local full regression: `257` tests passed in `76.312s`.
4. Production Compose configuration validation: passed.
5. Production migrations: `0034`, `0035` and `0036` applied successfully.
6. Production deploy check: passed with no errors.
7. Focused HMRC server verification: `26` tests passed in `8.660s`.
8. Empty-endpoint HMRC OAuth regression: `32` tests passed in `26.362s`.
9. Final full Hetzner regression: `257` tests passed in `261.665s`.
10. Final public health request: HTTP 200 with `{"status": "ok"}`.
11. Final application logs: no `Traceback`, `ERROR` or `CRITICAL` entries.

The full suite included six-stage end-to-end verification across six synthetic
tenants. All provider filing scenarios remained dry runs and produced no live
submission.

## Production security verification

- Runtime PostgreSQL role: `ledgerhouse_app`.
- Runtime role is not a superuser and cannot bypass row-level security.
- `DEBUG=False`.
- HTTPS redirection enabled.
- Session and CSRF cookies marked secure.
- Gunicorn is bound only to `127.0.0.1:8000` on the host.
- Caddy is the public TLS entry point.
- Companies House sending remains disabled. Its locally stored live-readiness
  flag does not itself transmit a filing.

The migration process emits the expected `accounting.W001` warning because it
temporarily uses the schema-owner account. The running web service was checked
separately and uses the restricted role.

## Browser verification

Routes checked:

- `https://ledgerhouse1.finaccord.pro/healthz/`
- `https://ledgerhouse1.finaccord.pro/login/`
- `https://ledgerhouse1.finaccord.pro/integrations/hmrc/services/`

Results:

- Health endpoint returned HTTP 200.
- Login page rendered with the LedgerHouse branding, username and password
  controls, and sign-in command.
- Unauthenticated HMRC workspace access redirected to the login page.
- Desktop viewport: no horizontal overflow and no browser console errors.
- Mobile viewport: no page, input or button overflow and no browser console
  errors.

## Source identity checks

The deployed hashes for the following files exactly matched the local tested
files:

- `accounting/hmrc_xml.py`
- `accounting/hmrc_income_tax.py`
- `accounting/hmrc_services.py`
- `templates/accounting/hmrc_services_workspace.html`

## Files changed during this deployment pass

- `deploy/hetzner/deploy_ledgerhouse.sh`
- `ledgerhouse/settings.py`
- `docker-compose.prod.yml`
- `docs/testing/hetzner_deployment_verification_2026_08_24.md`

The complete current LedgerHouse source tree was deployed. Existing server
secrets and the PostgreSQL data volume were preserved.

## External boundaries

- HMRC service approval and production credentials remain service-specific.
- Current CT600, RTI, CIS and Self Assessment XML bodies still require their
  official HMRC schema/RIM packs and recognition testing.
- A healthy Hetzner deployment does not prove HMRC acceptance.
- No live HMRC filing should be enabled until the relevant service approval,
  client authority, credentials, fraud-prevention data and provider validation
  route have all been confirmed.
- `ledgerhouse.finaccord.pro` is not the active hostname. The verified live
  hostname is `ledgerhouse1.finaccord.pro`.

