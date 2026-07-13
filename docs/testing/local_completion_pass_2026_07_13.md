# Local Completion Pass - 2026-07-13

## Scope

This pass covers the local-only work requested before returning to paid server deployment or production government filing.

## Built

- In-app practice client management at `/practice/clients/`.
- Client creation with a starter chart of accounts.
- Ledger approval action from `/practice/ledger/`.
- Evidence review status actions from `/practice/evidence/`.
- Bank review status actions from `/practice/banking/`.
- Review-state fields for evidence documents and bank transactions.
- Admin fallback visibility for the new review fields.
- Expanded `seed_db` demo data across six realistic companies with:
  - open client questions,
  - unlinked evidence,
  - unmatched bank lines,
  - supplier invoices awaiting review.
- Production filing blocker documentation for HMRC and Companies House.
- RLS/grant correction for `ClientRequest` so restricted-role local and production-style runs can use client question workflows.

## Automated Verification

Commands run:

```powershell
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py seed_db
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py
docker compose exec -T web python -m pytest
```

Results:

- Migrations applied successfully through `0014_fix_clientrequest_rls_setting`.
- `seed_db` rebuilt all six demo companies successfully.
- Django system check passed.
- Migration drift check passed with no changes detected.
- Focused workflow suite passed: 17 tests.
- Full test suite passed: 97 tests.

## Browser Verification

Using the in-app browser against `http://localhost:8000`:

- `/practice/clients/` rendered `Client management` with six seeded clients and a create-client form.
- `/practice/banking/` rendered six unmatched bank rows and six action forms.
- `/practice/evidence/` rendered seeded evidence rows and action forms.
- `/practice/ledger/?status=RequiresReview` rendered six review journals and approval forms.
- Submitted a bank action and received: `Bank line marked ReadyToPost.`
- Submitted an evidence action and received: `Evidence marked ReadyForPosting.`
- Submitted a ledger approval and received: `Journal approved and marked Posted.`

## Still Externally Blocked

- Real HMRC production filing.
- Real Companies House filing.
- Live bank-feed provider integration.
- Production deployment while server cost is intentionally paused.
