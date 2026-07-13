# Practice Live Controls Testing

Date: 2026-07-13

## Scope

This record covers replacing the practice dashboard placeholder roadmap card with live operational control points.

## Changes Tested

- Removed the visible `Next build` / `Product workflows` dashboard card.
- Added live practice action counts for:
  - open client questions
  - VAT reviews awaiting client approval
  - VAT reviews ready to file
- Added dashboard links into the workbench, VAT workspace and client reports.
- Added an anchor to the practice workbench section.

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
- Focused client portal/practice suite: `13 passed, 11 warnings`.
- Full suite: `93 passed, 23 warnings`.

Warnings observed:

- Django warns that `/app/staticfiles/` does not exist during tests. This is existing test-environment noise and did not block the workflow.

## Browser Smoke Tests

Browser path tested in the in-app browser:

1. Opened `http://localhost:8000/practice/`.
2. Confirmed the page loaded with title `LedgerHouse | Portfolio`.
3. Confirmed the old `Next build` text is not present.
4. Confirmed the live controls card rendered:
   - Client questions count
   - VAT awaiting client approval count
   - VAT ready to file count
   - Management reports link
5. Confirmed the practice workbench anchor exists.

## Result

The practice dashboard now reflects working local workflows instead of describing future build items.
