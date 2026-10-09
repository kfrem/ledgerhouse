# LedgerHouse Local Product Hardening Pass - 2026-07-21

## Scope

This pass continued local-only LedgerHouse development without HMRC. It focused on making the product more useful as a client/practice accounts department and adding a repeatable acceptance command for future developers.

## Built

1. Local upload intelligence now classifies non-bank uploads into evidence categories.
2. Upload intake now extracts a simple gross amount from text/PDF-like content where available.
3. Upload intake now suggests local nominal account codes for sales, purchases, receipts, payroll and tax documents.
4. Client upload messages now state the classification result.
5. Management report context now includes plain-English summaries.
6. Management report context now includes a local workflow board.
7. Management report context now includes local accounting adjustment checks.
8. Management CSV export now includes summaries, workflow board and accounting checks.
9. Management PDF export now includes summaries, workflow board and accounting checks.
10. Client portal now shows a plain-English accountant summary section.
11. Management report page now shows workflow board and accounting adjustment sections.
12. New `local_acceptance_suite` command proves local readiness without HMRC.

## New Command

```powershell
docker exec ledgerhouse_web python manage.py local_acceptance_suite --strict --output docs/testing/local_acceptance_suite_2026_07_21.md --username loop-engineering
```

Result:

All local acceptance checks passed.

The command checks:

- Accounts department 8/8 local phase coverage.
- Client portal page render.
- Practice dashboard page render.
- Accounts department page render.
- Management report page render.
- Management CSV download.
- Management PDF download.
- Management pack download.
- Accounts department pack download.
- Client data ZIP download.
- No-HMRC handover ZIP generation.

Generated report:

`docs/testing/local_acceptance_suite_2026_07_21.md`

## Tests Run

Focused accounts department suite:

```powershell
docker exec ledgerhouse_web python manage.py test accounting.tests.test_accounts_department_suite --noinput
```

Result:

`Ran 13 tests in 10.002s - OK`

Focused client/report tests:

```powershell
docker exec ledgerhouse_web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_pdf_upload_stores_evidence_document accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf --noinput
```

Result:

`Ran 2 tests in 5.041s - OK`

Full client workflow suite:

```powershell
docker exec ledgerhouse_web python manage.py test accounting.tests.test_client_portal_workflows --noinput
```

Result:

`Ran 31 tests in 87.058s - OK`

Full regression:

```powershell
docker exec ledgerhouse_web python manage.py test --noinput
```

Result:

`Ran 149 tests in 219.146s - OK`

## Browser Checks

Client portal:

`http://127.0.0.1:8000/`

Confirmed:

- Your accounts department.
- What the numbers mean.
- What happens after you upload records.
- Upload anything finance-related.
- No horizontal overflow detected.

Management report:

`/reports/<tenant-id>/`

Confirmed:

- What the figures mean.
- Workflow board.
- Adjustments to review locally.
- What should happen next.
- No horizontal overflow detected.

## Corrections During The Loop

1. The first strict acceptance command failed because Django test-client requests used `testserver`, which this project does not allow in `ALLOWED_HOSTS`.
2. Fixed the command to use `HTTP_HOST="localhost"`.
3. Reran strict acceptance; all checks passed.
4. Upload classifier originally matched `invoice total` as sales because `invoice to` was too broad.
5. Tightened the sales invoice rule and reran focused tests; classification passed.
6. Browser check found the management report workflow section was present but not explicitly labelled enough.
7. Updated the heading to `Workflow board: where the finance-office work sits` and rechecked in browser.

## Remaining External Boundaries

- HMRC live production approval and OAuth.
- Companies House live filing approval.
- Bank-feed provider access.
- Payment provider setup.
- DNS/server deployment.
- Legal/compliance review for production trading.

## Developer Takeover

Run this first after future local changes:

```powershell
docker exec ledgerhouse_web python manage.py local_acceptance_suite --strict --output docs/testing/local_acceptance_suite_latest.md --username loop-engineering
```

Then run:

```powershell
docker exec ledgerhouse_web python manage.py test --noinput
```

This pass is local-only and does not claim HMRC or Companies House production approval.
