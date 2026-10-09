# Accounts Department Workflow Pass

Date: 2026-07-16

## Purpose

This pass continued local product development by making LedgerHouse feel more like a complete outsourced accounts department instead of a collection of technical accounting screens.

## Completed

- Added a derived accounts department workflow helper in `accounting/views.py`.
- Exposed the workflow on the client portal.
- Exposed the same service pipeline on the practice client file.
- Added workflow stages for:
  - Source documents
  - Bank matching
  - Bookkeeping
  - Management reporting
  - Statutory compliance
  - Advice and questions
- Styled the workflow as a first-class product panel with responsive layout.
- Updated tests so the workflow is now part of the protected client/practice experience.

## Verification

Commands run:

```text
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows
```

Result:

```text
System check identified no issues.
Focused client portal workflow suite: 24 tests OK.
```

Browser smoke checks confirmed:

- Client portal includes `Accounts department workflow`.
- Client portal includes `Source documents` and `Statutory compliance`.
- Practice client file includes `Client service pipeline`.
- Practice client file includes `Management reporting`.

## Notes

This work did not require a new database migration. The workflow is calculated from existing uploaded evidence, bank transactions, journals, statutory review records and client questions.
