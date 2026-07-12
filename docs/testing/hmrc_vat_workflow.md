# HMRC VAT Workflow Testing

Date: 2026-07-12

## Scope

This record covers the local LedgerHouse HMRC VAT workflow after adding the practice checklist and client approval gate:

- HMRC VAT workspace rendering
- VAT obligation sync review creation
- Backfill of review records for obligations synced before the `VatReview` table existed
- Practice checklist updates
- Client VAT approval page
- Submission blocking before approval
- Submission readiness after approval
- Django migrations and full automated test suite

## Environment

- Runtime: Docker Compose
- Services checked: `ledgerhouse_db`, `ledgerhouse_web`
- App URL: `http://localhost:8000`
- Database migration added: `accounting/migrations/0010_vatreview.py`
- External HMRC sandbox filing was not re-submitted during this browser smoke pass. The browser test stopped once the local app showed the return was ready to submit, to avoid sending another sandbox return unnecessarily.

## Automated Tests

Commands run:

```powershell
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web pytest accounting/tests/test_hmrc_sandbox.py -q
docker compose exec -T web pytest -q
```

Results:

- `python manage.py migrate`: applied `accounting.0010_vatreview` successfully.
- `python manage.py check`: passed, `System check identified no issues`.
- `python manage.py makemigrations --check --dry-run`: passed, `No changes detected`.
- Focused HMRC VAT suite: `19 passed, 12 warnings`.
- Full suite: `88 passed, 18 warnings`.

Warnings observed:

- Django warns that `/app/staticfiles/` does not exist during tests. This is already present test-environment noise and does not block the workflow.

## Browser Smoke Tests

Browser path tested in the in-app browser:

1. Opened `http://localhost:8000/integrations/hmrc/vat/`.
2. Confirmed the page title was `LedgerHouse | HMRC VAT workspace`.
3. Confirmed the workspace rendered:
   - `VAT filing control`
   - practice checklist controls
   - client review page link
   - disabled `Complete approvals first` filing button before approvals
4. Found and fixed a backfill issue: existing obligations from before the new review table did not yet have `VatReview` records, so saving the checklist failed with `Sync HMRC obligations before reviewing this period`.
5. Retested after fix:
   - workspace backfilled missing reviews from saved obligations on page load
   - open period `18A2` checklist saved successfully
   - status changed to `Awaiting client`
6. Opened `http://localhost:8000/vat/review/?company=<local-company-id>`.
7. Confirmed client approval page rendered:
   - `Review VAT before filing`
   - `18A2` showed practice checklist `Complete`
   - `18A2` had enabled `Approve for filing`
   - `18A1` stayed disabled as `Waiting for accountant review`
8. Approved `18A2` from the client page.
9. Confirmed approval result:
   - success message: `VAT period 18A2 approved for filing.`
   - `18A2` status changed to `ClientApproved`
   - approval button changed to disabled `Approved`
10. Returned to the practice VAT workspace.
11. Confirmed final filing gate:
   - `18A2` status changed to `Ready to submit`
   - client approval strip showed `Approved`
   - `Submit sandbox return` button became enabled

## Regression Found And Fixed

Issue:

- Stored obligations created before the new `VatReview` model existed did not have matching review rows.
- This blocked checklist saving until obligations were synced again.

Fix:

- Added `_ensure_vat_review_for_obligation(...)` in `accounting/views.py`.
- The VAT workspace now creates or updates a review row from each stored obligation whenever the page is loaded or obligations are synced.
- Added regression test: `test_vat_workspace_backfills_reviews_for_existing_synced_obligations`.

## Remaining Constraints

- Production HMRC credentials are not configured in this local app.
- HMRC sandbox tokens are stored locally for development. Before production use, token storage should be encrypted and refresh-token handling should be hardened.
- Final HMRC submission was tested by automated mocked tests and earlier sandbox work; this browser pass deliberately stopped before another external sandbox submission.
