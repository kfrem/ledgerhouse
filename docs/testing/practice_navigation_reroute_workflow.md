# Practice Navigation Reroute Workflow

## Scope

This records the local verification for replacing routine practice links that still pointed to Django admin even though product screens now exist.

## Behaviour Covered

- Dashboard VAT links open the HMRC VAT workspace.
- Dashboard client-question queue rows open the in-app client file.
- Client-file unmatched bank rows open the in-app banking review screen.
- Client-file VAT rows open the HMRC VAT workspace for the selected company.
- HMRC status navigation opens the HMRC VAT workspace instead of the admin VAT table.
- Admin remains available only where the product explicitly labels it as an admin or data fallback.

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

## 2026-07-13 Local Result

- `docker compose exec -T web python manage.py check` passed.
- `docker compose exec -T web python manage.py makemigrations --check --dry-run` passed with no changes detected.
- `docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py` passed: 16 tests.
- `docker compose exec -T web python -m pytest` passed: 96 tests.
