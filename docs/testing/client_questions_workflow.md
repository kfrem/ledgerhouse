# Client Questions Workflow Testing

Date: 2026-07-13

## Scope

This record covers the local client-to-practice question workflow:

- Client portal support form
- Validation for missing subject/message
- Client request persistence
- Client portal request history
- Practice dashboard `Client questions` queue
- Admin registration for request review

## Changes Tested

- Added `ClientRequest` model.
- Added `accounting/migrations/0011_clientrequest.py`.
- Added `ClientRequest` to Django admin.
- Added client question submission to the existing client portal.
- Added recent client question history to the client portal support panel.
- Added unresolved client questions to the practice dashboard workbench.
- Updated local seed cleanup to remove old client requests on reseed.

## Automated Tests

Commands run:

```powershell
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web pytest accounting/tests/test_client_portal_workflows.py -q
docker compose exec -T web pytest -q
```

Results:

- `python manage.py migrate`: applied `accounting.0011_clientrequest` successfully.
- `python manage.py check`: passed, `System check identified no issues`.
- `python manage.py makemigrations --check --dry-run`: passed, `No changes detected`.
- Focused client portal suite: `11 passed, 9 warnings`.
- Full suite: `91 passed, 21 warnings`.

Warnings observed:

- Django warns that `/app/staticfiles/` does not exist during tests. This is existing test-environment noise and did not block the workflow.

## Browser Smoke Tests

Browser path tested in the in-app browser:

1. Opened `http://localhost:8000/?company=<local-company-id>`.
2. Confirmed the client portal loaded with title `LedgerHouse | Client portal`.
3. Confirmed the support panel rendered a real form and `Send question` button.
4. Submitted a unique support request:
   - Category: `Cash flow`
   - Priority: `High`
   - Subject: `Browser smoke cash flow <timestamp>`
5. Confirmed the client portal showed:
   - success message: `Your question has been sent to the accounts team.`
   - the submitted subject in the support history
   - status `Open`
6. Opened `http://localhost:8000/practice/`.
7. Confirmed the practice dashboard loaded with title `LedgerHouse | Portfolio`.
8. Confirmed the workbench rendered `Client questions`.
9. Confirmed the submitted request appeared in the practice queue with:
   - company `CareCo Limited`
   - category `Cash flow`
   - priority `High`

## Result

The client no longer has a dead `Start a question` button. Questions can now be submitted locally and appear immediately for the accountant/practice team to triage.
