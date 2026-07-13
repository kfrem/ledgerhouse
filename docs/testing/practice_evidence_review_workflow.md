# Practice Evidence Review Workflow

## Scope

This records the local verification for the in-app practice evidence review screen.

## Behaviour Covered

- Practice users can open `/practice/evidence/` without using Django admin.
- The evidence stream can be filtered by company.
- Uploaded evidence documents show filename, uploader, content type and upload time.
- Document rows link back to the in-app client file.
- Linked and unlinked evidence counts are surfaced for review control.
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
http://localhost:8000/practice/evidence/
```

Verify:

- The page heading is `Evidence review`.
- Summary metrics render for documents shown, linked, unlinked and client.
- The upload stream is visible.
- A document row opens `/practice/clients/<tenant-id>/` rather than a Django admin change form.

## 2026-07-13 Local Result

- `docker compose exec -T web python manage.py check` passed.
- `docker compose exec -T web python manage.py makemigrations --check --dry-run` passed with no changes detected.
- `docker compose exec -T web python -m pytest accounting/tests/test_client_portal_workflows.py` passed: 16 tests.
- `docker compose exec -T web python -m pytest` passed: 96 tests.
- Browser smoke seeded `Browser Smoke Client Ltd` locally and verified:
  - `/practice/evidence/` rendered the `Evidence review` page.
  - summary metrics and upload stream were visible.
  - the seeded `browser-smoke-receipt.pdf` row was visible.
  - the row linked to `/practice/clients/<tenant-id>/`.
  - no matching upload stream row linked to `/admin/accounting/evidencedocument/`.
