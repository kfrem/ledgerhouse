# Practice Banking Review Workflow

## Scope

This records the local verification for the in-app practice banking review screen.

## Behaviour Covered

- Practice users can open `/practice/banking/` without using Django admin.
- The screen lists only imported bank transactions that do not have a `BankReconciliation`.
- The company filter limits the queue to one client.
- Each unmatched transaction links back to the in-app client file for the relevant company.
- The old admin bank transaction list remains available only as a maintenance fallback.

## Automated Checks

Run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest accounting/tests/test_client_portal_workflows.py
python -m pytest
```

Expected result:

- Django system checks pass.
- No model migrations are required.
- The focused workflow suite passes.
- The full test suite passes.

## Browser Smoke Check

Open:

```text
http://localhost:8000/practice/banking/
```

Verify:

- The page heading is `Unmatched bank review`.
- Summary metrics render for unmatched lines, net value, clients affected and current filter.
- The matching queue is visible.
- A transaction row opens `/practice/clients/<tenant-id>/` rather than a Django admin change form.

## 2026-07-13 Local Result

- `docker compose exec -T web python manage.py check` passed.
- `docker compose exec -T web python manage.py makemigrations --check --dry-run` passed with no changes detected.
- `docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py` passed: 14 tests.
- `docker compose exec -T web python -m pytest` passed: 94 tests.
- Browser smoke seeded `Browser Smoke Client Ltd` locally and verified:
  - `/practice/banking/` rendered the `Unmatched bank review` page.
  - the seeded `Browser smoke subscription` row was visible.
  - the row linked to `/practice/clients/<tenant-id>/`.
  - no matching queue row linked to `/admin/accounting/banktransaction/`.
