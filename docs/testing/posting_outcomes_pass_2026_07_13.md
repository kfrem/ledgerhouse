# Posting Outcomes Pass - 2026-07-13

## Scope

This pass turns practice review actions into accounting outcomes and audit records.

## Built

- Bank lines marked `ReadyToPost` now create a balanced `BankPayment` or `BankReceipt` journal.
- The bank posting also creates a `BankReconciliation` link and marks the bank line `Reviewed`.
- Evidence marked `ReadyForPosting` now creates a linked `EvidenceReview` journal.
- Evidence review journals are balanced zero-value review records because the document alone does not safely provide an amount.
- Ledger approvals now create immutable `AuditEvent` records.
- Bank and evidence review actions now create immutable `AuditEvent` records.
- Client portal upload history now shows processing state instead of a generic `Stored` label.

## Automated Verification

Commands run:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py
docker compose exec -T web python manage.py seed_db
docker compose exec -T web python -m pytest
```

Results:

- System check passed.
- Migration drift check passed with no changes detected.
- Focused workflow tests passed: 17 tests.
- Seed rebuild passed for all six demo companies.
- Full test suite passed: 97 tests.

## Browser Render Smoke

Verified in the in-app browser:

- `/practice/banking/` rendered `Unmatched bank review` with six rows and action controls.
- `/practice/evidence/` rendered `Evidence review` with seeded evidence rows and action controls.
- `/practice/ledger/?status=RequiresReview` rendered `Ledger review` with six review rows and approval controls.
- Client portal rendered seeded CareCo data and upload processing status text.

## Production Confidence Boundary

This was verified in Docker against PostgreSQL with migrations, RLS policies, triggers, and the same Django code path used by deployment.

What cannot be guaranteed until server deployment:

- DNS/TLS correctness.
- Live HMRC and Companies House credentials.
- Live bank-feed provider behaviour.
- Provider rate limits and production API responses.
- Server filesystem, backup, and environment-variable configuration.
