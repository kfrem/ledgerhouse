# Practice Client File Workflow Testing

Date: 2026-07-13

## Scope

This record covers the local practice-side client file workflow:

- Portfolio client rows opening an in-app client file
- Client-level practice summary cards
- Client-level action shortcuts
- Client queues for questions, uploads, unmatched bank lines and ledger review
- Client VAT/report/ledger surfaces linked from one place

## Changes Tested

- Added `practice_client_detail` view.
- Added route `/practice/clients/<tenant_id>/`.
- Added `templates/accounting/practice_client_detail.html`.
- Updated practice dashboard client rows to open the in-app client file instead of going straight to Django admin.
- Added automated coverage for the client file view and dashboard links.

## Automated Tests

Commands run:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web pytest accounting/tests/test_client_portal_workflows.py -q
docker compose exec -T web pytest -q
```

Results:

- `python manage.py check`: passed, `System check identified no issues`.
- `python manage.py makemigrations --check --dry-run`: passed, `No changes detected`.
- Focused client portal/practice suite: `12 passed, 10 warnings`.
- Full suite: `92 passed, 22 warnings`.

Warnings observed:

- Django warns that `/app/staticfiles/` does not exist during tests. This is existing test-environment noise and did not block the workflow.

## Browser Smoke Tests

Browser path tested in the in-app browser:

1. Opened `http://localhost:8000/practice/`.
2. Confirmed the portfolio loaded with title `LedgerHouse | Portfolio`.
3. Confirmed the CareCo client row links to `/practice/clients/<tenant_id>/`.
4. Opened `http://localhost:8000/practice/clients/<tenant_id>/`.
5. Confirmed the page loaded with title `LedgerHouse | Client file`.
6. Confirmed the page rendered `CareCo Limited`.
7. Confirmed summary cards rendered:
   - Revenue
   - Costs
   - Profit
   - VAT due
8. Confirmed action links rendered:
   - Client portal
   - VAT workspace
   - Management report
   - Admin record
9. Confirmed queue panels rendered:
   - Questions
   - Uploads
   - Unmatched bank
   - Ledger review
10. Confirmed the client file includes VAT returns and recent postings sections.

## Result

The practice user can now open an operational client file inside the LedgerHouse UI, instead of being sent straight to Django admin for routine client review.
