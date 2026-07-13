# LedgerHouse External Test Deployment Runbook

Date: 2026-07-13

Purpose: steps to follow when the user is ready to redeploy LedgerHouse for an external client/tester without uncontrolled costs.

## Before Creating A Server

- Confirm the user wants to start hosting cost again.
- Confirm the target monthly server budget.
- Confirm backups on/off.
- Confirm no snapshots, no volumes, no floating IP and no load balancer unless deliberately approved.
- Confirm DNS target for `ledgerhouse.finaccord.pro`.
- Confirm production secrets are available locally but not in Git.

## Required Environment Variables

- `DEBUG=False`
- `SECRET_KEY`
- `FIELD_ENCRYPTION_KEY`
- `DATABASE_URL`
- `ALLOWED_HOSTS=ledgerhouse.finaccord.pro`
- `CSRF_TRUSTED_ORIGINS=https://ledgerhouse.finaccord.pro`
- `SECURE_TLS=True`
- `HMRC_CLIENT_ID` after HMRC approval
- `HMRC_CLIENT_SECRET` after HMRC approval
- `HMRC_VENDOR_PUBLIC_IP`
- `HMRC_VENDOR_VERSION`
- `COMPANIES_HOUSE_API_KEY` if Companies House lookup is enabled

## Deployment Steps

1. Build Docker image.
2. Apply migrations.
3. Collect static files.
4. Create/use restricted PostgreSQL application role.
5. Start application behind HTTPS reverse proxy.
6. Confirm Caddy/HTTPS certificate issuance.
7. Confirm `/privacy/` and `/terms/` are publicly reachable.
8. Confirm `/login/` renders.
9. Confirm authenticated client portal renders.
10. Confirm authenticated practice dashboard renders.
11. Confirm file upload works.
12. Confirm report PDF/CSV/ZIP downloads work.
13. Confirm HMRC status page does not expose secrets.
14. Confirm Companies House lookup if key is enabled.

## Post-Deploy Verification

Run:

```powershell
python manage.py check --database default
python manage.py check_production_readiness --strict
python manage.py test
```

Browser checks:

- `/login/`
- `/`
- `/practice/`
- `/practice/evidence/`
- `/practice/banking/`
- `/practice/ledger/`
- `/integrations/hmrc/`
- `/integrations/hmrc/vat/`
- `/integrations/companies-house/`
- `/privacy/`
- `/terms/`

Security/accessibility checks:

- Run OWASP ZAP baseline against the live HTTPS domain.
- Run accessibility scan against login, client portal, practice dashboard, HMRC VAT workspace and client VAT review.
- Record evidence in `docs/compliance/`.

## Cost Control Rules

- Create only one small server unless the user explicitly approves more.
- Do not enable backups unless the user explicitly approves the additional cost.
- Do not create volumes, snapshots, floating IPs or load balancers unless explicitly approved.
- Delete the server after external testing if the user wants to stop hourly charges.

## Rollback

- Keep local Docker development environment as the source of truth.
- Before deletion, confirm whether a database dump is needed.
- Export logs and deployment notes into `docs/deployment/`.
- Delete server and confirm Hetzner console shows no running chargeable resources.
