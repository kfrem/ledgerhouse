# LedgerHouse

LedgerHouse is a UK-focused, accountant-supervised accounts-department
application for small and medium businesses. Clients upload records and view
plain-English finance information. Practice users review evidence, bookkeeping,
bank activity, approvals, reports, month-end work and statutory readiness.

LedgerHouse is a Django modular monolith backed by PostgreSQL. PostgreSQL is
mandatory because ledger balance, period locks, VAT locks, audit immutability
and tenant controls rely on database constraints and policies.

## Local prerequisites

- Docker Desktop with Docker Compose v2
- At least 4 GB of available Docker memory
- Port `8000` for the web application and port `5432` for PostgreSQL

No HMRC, Companies House, bank-feed, payment or email credentials are required
to run and test the local product.

## Start locally

```powershell
Copy-Item .env.example .env
# Set a long random SECRET_KEY and a local-only POSTGRES_PASSWORD in .env.
# Do not use either value outside this local machine.
docker compose up -d --build
docker compose ps
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py check --database default
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). The local trial account
is `admin` / `admin2`. This account is for a local development database only;
never use it in a public deployment.

To create or refresh synthetic data without entering any real client data:

```powershell
docker compose exec -T web python manage.py seed_db
```

## Local verification

Run these commands after any product change. They do not make a government
filing or contact any external provider.

```powershell
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py local_acceptance_suite --strict --output docs/testing/local_acceptance_suite_latest.md --username loop-engineering
docker compose exec -T web python manage.py test --noinput
```

## Local backup rehearsal

Create a checksummed local data archive and prove that it can be deserialised
without altering the running database:

```powershell
docker compose exec -T web python manage.py backup_local_database --restore-rehearsal
```

The archive is written beneath `backups/`, which is ignored by Git. The
rehearsal restores only inside a transaction and rolls it back; it is not a
substitute for a production hosting-provider backup and restore drill.

The acceptance report verifies client and practice pages, report downloads,
PDF and ZIP generation and the no-HMRC handover pack. The Django suite verifies
ledger integrity, tenant separation, import/review workflows, exports,
Companies House local controls and local integration boundaries.

The practice HMRC service register is available at
`/integrations/hmrc/services/`. It separately tracks VAT MTD, Corporation Tax,
PAYE RTI, CIS, Income Tax MTD and Self Assessment. Client tax references and
prepared payloads are encrypted at rest. Local preflight never means HMRC
acceptance: each service remains unable to submit until its own official HMRC
test route, approval and credentials have been verified and explicitly enabled.

The workspace also shows the complete Income Tax MTD subscription matrix and
prepares separate quarterly, annual, SA100, SA800 and SA900 cases.
`accounting.hmrc_xml` implements the generic Transaction Engine envelope,
IRmark generation, polling, response parsing and fail-closed transport. It
accepts only a service body generated and validated against HMRC's current
schema; it does not invent or silently accept an unvalidated return body.

## Environment configuration

Copy `.env.example` to `.env` only when overriding Compose defaults or using a
production-style configuration. `.env` is ignored by Git.

The following credentials are external boundaries and must be stored in
environment variables or the documented local secret files, never in source
code or Git:

- `HMRC_CLIENT_ID`, `HMRC_CLIENT_SECRET`
- `COMPANIES_HOUSE_API_KEY`
- `COMPANIES_HOUSE_FILING_PRESENTER_ID`
- `COMPANIES_HOUSE_FILING_AUTHENTICATION_VALUE`
- `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `SECRET_KEY`

See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete production environment
variable list and restricted database role setup.

## Production deployment

Production is deliberately gated. Do not use the local Compose configuration
on a public server. Configure a non-development `.env`, a restricted runtime
database role, HTTPS and backups, then follow:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml run --rm web python manage.py check --database default --deploy --fail-level ERROR
```

Before real client data is admitted, comply with the gates in
[DECISIONS.md](DECISIONS.md) and the production checklist in
[docs/deployment/production_readiness_checklist_2026_07_13.md](docs/deployment/production_readiness_checklist_2026_07_13.md).

## External boundaries

Local automated tests include controlled test doubles for bank data and
notifications. HMRC preparation cases and validators demonstrate LedgerHouse's
local behaviour; they do not create accepted records, provider receipts or
accounting side effects. Real HMRC filing, Companies House
production filing, bank feeds, email delivery, payment collection, DNS/TLS and
backup restoration require the relevant external approvals, credentials or
service accounts.

See [docs/integrations/production_filing_blockers.md](docs/integrations/production_filing_blockers.md)
for the current external-filing boundary and
[docs/development/STATE_OF_BUILD_2026_07_22.md](docs/development/STATE_OF_BUILD_2026_07_22.md)
for the current local build assessment.

## Stop locally

```powershell
docker compose down
```

This stops containers but keeps the local PostgreSQL volume. To deliberately
erase local development data, use `docker compose down -v` only after making a
backup and confirming that no data needs to be retained.
