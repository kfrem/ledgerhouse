# LedgerHouse Production Readiness Checklist

Date: 2026-07-13

This checklist separates what can be completed locally from what must wait for external credentials, public hosting, HMRC approval or legal review.

## Local Command

Run:

```powershell
docker compose exec -T web python manage.py check_production_readiness
```

For a production environment, run:

```powershell
python manage.py check_production_readiness --strict
```

## Required Before Public Paid Launch

- `DEBUG=False`.
- Real `SECRET_KEY` supplied outside Git.
- Real `FIELD_ENCRYPTION_KEY` supplied outside Git.
- HTTPS enforced through the reverse proxy and Django production settings.
- PostgreSQL used as the database backend.
- Restricted PostgreSQL application role used in production, not a superuser or BYPASSRLS role.
- Public privacy notice legally reviewed.
- Terms and conditions legally reviewed.
- Data processing agreement prepared.
- Backup and restore drill completed.
- Production security and accessibility checks repeated against the final domain.

## Required Before Live HMRC API Calls

- HMRC production credentials approved by HMRC.
- HMRC production client ID and secret saved outside Git.
- `HMRC_VENDOR_PUBLIC_IP` set to the real egress/ingress IP used for HMRC calls.
- `HMRC_VENDOR_VERSION` set to the released LedgerHouse version.
- Final live OAuth journey tested with a controlled authorised account.
- Filing/submission buttons kept disabled until a controlled production filing test is deliberately approved.

## Required Before Companies House API Use

- Companies House API key saved outside Git.
- Company search/profile retrieval smoke-tested.
- Filing date and confirmation statement tracking reviewed against a known company.

## Required Before External Client Testing

- Public deployment restored only when the user is ready to incur hosting cost.
- DNS and HTTPS confirmed for `ledgerhouse.finaccord.pro`.
- Smoke tests run against the public domain.
- ZAP baseline and accessibility scans repeated against the public domain.
- Test client onboarding walkthrough completed.

## Current Local Status

Completed locally:

- HMRC production credentials request submitted.
- Security baseline committed.
- Token encryption implemented.
- Tenant user access implemented.
- Public privacy and terms routes added.
- Fraud-prevention headers implemented and validated in HMRC sandbox validator.
- Full local suite passed with 103 tests.

Blocked externally:

- HMRC approval.
- Public deployment checks while server is intentionally paused.
- Live HMRC OAuth/filing.
- Legal review of customer documents.
- Production backup restore drill.
