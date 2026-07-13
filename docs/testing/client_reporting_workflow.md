# Client Reporting Workflow Testing

Date: 2026-07-13

## Scope

This record covers the local client-facing management report work completed after the VAT approval workflow:

- Client portal reports area
- In-app HTML management report
- CSV management report export
- PDF management report export
- Route wiring and template rendering

## Changes Tested

- Added `management_report_view` at `/reports/<tenant_id>/`.
- Added `templates/accounting/management_report.html`.
- Updated the client portal report area to show:
  - `View`
  - `CSV`
  - `PDF`
- Removed the visible `Coming` placeholder from the reports area.
- Kept CSV/PDF export generation using the existing report engine.

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
- Focused client portal suite: `9 passed, 7 warnings`.
- Full suite: `89 passed, 19 warnings`.

Warnings observed:

- Django warns that `/app/staticfiles/` does not exist during tests. This is existing test-environment noise and did not block the workflow.

## Browser Smoke Tests

Browser path tested in the in-app browser:

1. Opened `http://localhost:8000/?company=<local-company-id>`.
2. Confirmed the client portal loaded with title `LedgerHouse | Client portal`.
3. Confirmed the reports panel no longer contains `Coming`.
4. Confirmed the report links rendered:
   - `/reports/<tenant_id>/` as `View`
   - `/reports/<tenant_id>/csv/` as `CSV`
   - `/reports/<tenant_id>/pdf/` as `PDF`
5. Opened `http://localhost:8000/reports/<tenant_id>/`.
6. Confirmed the page loaded with title `LedgerHouse | Management report`.
7. Confirmed the page rendered the selected company, `CareCo Limited`.
8. Confirmed summary cards rendered for:
   - Revenue
   - Costs
   - Profit
   - VAT due
9. Confirmed report sections rendered for:
   - What has been processed
   - Filed returns
   - Recent bookkeeping
   - Recent files
10. Confirmed top actions rendered:
   - Client portal
   - PDF
   - CSV

## Export Testing

CSV and PDF exports were verified through automated Django tests:

- `management_report_csv(...)` includes the company and revenue lines.
- `management_report_pdf(...)` returns bytes beginning with `%PDF`.
- `/reports/<tenant_id>/csv/` returns HTTP 200 and `text/csv`.
- `/reports/<tenant_id>/pdf/` returns HTTP 200 and `application/pdf`.

The browser smoke pass did not separately download the files because the in-app browser runtime used for smoke testing does not expose `fetch` inside the local page context.

## Result

The client now has a real local management report page instead of a placeholder. The same report can be viewed in the app or exported as CSV/PDF.
