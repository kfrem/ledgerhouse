# Practice Ledger Review Workflow

## Scope

This records the local verification for the in-app practice ledger review screen.

## Behaviour Covered

- Practice users can open `/practice/ledger/` without using Django admin.
- The ledger stream can be filtered by company.
- The ledger stream can be filtered by journal status, including `RequiresReview`.
- Journal rows link back to the in-app client file.
- Django admin remains available only as a maintenance fallback.

## Automated Checks

Run:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py
docker compose exec -T web python -m pytest
```

Expected result:

- Django system checks pass.
- No model migrations are required.
- The focused workflow suite passes.
- The full test suite passes.

## Browser Smoke Check

Open:

```text
http://localhost:8000/practice/ledger/
```

Verify:

- The page heading is `Ledger review`.
- Summary metrics render for shown, posted, needs review and client.
- Review controls render for all, review and posted status filters.
- A journal row opens `/practice/clients/<tenant-id>/` rather than a Django admin change form.

## 2026-07-13 Local Result

- `docker compose exec -T web python manage.py check` passed.
- `docker compose exec -T web python manage.py makemigrations --check --dry-run` passed with no changes detected.
- `docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py` passed: 15 tests.
- `docker compose exec -T web python -m pytest` passed: 95 tests.
- Browser smoke seeded `Browser Smoke Client Ltd` locally and verified:
  - `/practice/ledger/?status=RequiresReview` rendered the `Ledger review` page.
  - summary metrics and review controls were visible.
  - the seeded `Browser smoke supplier invoice review` row was visible.
  - the row linked to `/practice/clients/<tenant-id>/`.
  - no matching posting stream row linked to `/admin/accounting/journal/`.
