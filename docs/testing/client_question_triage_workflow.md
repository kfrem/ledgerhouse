# Client Question Triage Workflow Testing

Date: 2026-07-13

## Scope

This record covers in-app practice triage for client questions:

- Updating a client question from the practice client file
- Marking a question `Open`, `InProgress`, or `Resolved`
- Recording resolver metadata for resolved questions
- Rendering success feedback and updated status

## Changes Tested

- Added POST handling to `practice_client_detail` for `update_client_request`.
- Added status controls to the `Questions` queue in `practice_client_detail.html`.
- Added styles for request triage controls.
- Added automated coverage for resolving a client question in-app.

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

1. Opened `http://localhost:8000/practice/clients/<tenant_id>/`.
2. Confirmed the page loaded with title `LedgerHouse | Client file`.
3. Confirmed a request triage form existed in the `Questions` queue.
4. Changed the first question status to `Resolved`.
5. Submitted the form from the UI.
6. Confirmed success message: `Client question marked Resolved.`
7. Confirmed the question row now showed `Cash flow | Resolved`.

## Result

The practice user can now triage client questions without leaving the LedgerHouse UI for Django admin.
