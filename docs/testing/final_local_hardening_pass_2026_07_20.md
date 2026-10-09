# LedgerHouse Final Local Hardening Pass

Date: 2026-07-20

Scope: local-only completion pass. This did not use live HMRC, Companies House, bank feeds, payment providers, DNS, public deployment, or external approvals.

## Objective

Complete the remaining local hardening that could be done without external help, then review, correct, test and document it for later scrutiny.

## Completed

### 1. Safer Local File Intake

Updated `accounting/intake.py` so empty uploads are rejected before they enter the evidence vault or bank import pipeline.

Behaviour now:

- Empty file payloads raise `ValueError("Uploaded file is empty.")`.
- No `EvidenceDocument` is created for an empty upload.
- Existing CSV, XLSX and document intake behaviour remains unchanged for valid files.

Why this matters:

- Prevents meaningless empty evidence records.
- Gives a clear local validation error.
- Improves integrity of client upload workflows.

### 2. Action-Oriented Management Reports

Updated `accounting/reports.py` so `management_report_context(...)` now includes generated `action_points`.

Action points are produced from local records such as:

- Unreviewed evidence.
- Unmatched bank transactions.
- Open client questions.
- Aged debtors.
- Aged creditors.
- Low cash runway.

Outputs updated:

- CSV management report.
- Standard PDF management report.
- Management pack PDF.
- HTML management report page.

Why this matters:

- Reports now tell the client/practice what to do next, not just what the figures are.
- The client-facing report is closer to a useful finance department pack.

### 3. HTML Report Page Finalisation

Updated `templates/accounting/management_report.html` to show the generated action points in the rendered app.

The report page now includes:

- `Action points`
- `What should happen next`
- Locally generated action items.

This was added after review showed that action points existed in exports but not in the browser report view.

## Review And Corrections

Review finding:

- The first implementation put action points into CSV/PDF outputs but not into the HTML management report.

Correction:

- Added an `Action points` section to the management report template.
- Extended the management report view test to verify the section renders in HTML.
- Reran focused and full regression tests after the correction.

## Tests Run

Focused upload/report test:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_empty_upload_is_rejected_before_intake accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_pdf_upload_stores_evidence_document accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf --noinput
```

Result: 3 tests passed.

Focused final report test after HTML correction:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_can_view_management_report_in_app accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_empty_upload_is_rejected_before_intake --noinput
```

Result: 3 tests passed.

Django checks:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

- System check passed with no issues.
- No migration changes detected.

Final full regression:

```powershell
docker compose exec -T web python manage.py test --noinput
```

Result: 119 tests passed.

The final full suite included the existing end-to-end verification across all six seeded demo tenants:

- CareCo Limited
- ConsultCo Consulting
- TradeCo Retail
- TechCo Software Ltd
- LogisticsCo Transport Ltd
- CharityCo Foundation

## Browser Review

Browser: Codex in-app browser.

URL:

```text
http://127.0.0.1:8000/reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/
```

Company reviewed: CareCo Limited.

Verified on rendered page:

- Page title: `LedgerHouse | Management report`.
- `Action points` section was visible.
- `What should happen next` was visible.
- Generated local action points appeared, including evidence review, bank matching, client questions, debtors, creditors and cash runway.

## Files Changed In This Pass

- `accounting/intake.py`
- `accounting/reports.py`
- `accounting/tests/test_client_portal_workflows.py`
- `templates/accounting/management_report.html`
- `docs/testing/final_local_hardening_pass_2026_07_20.md`

## What Another AI Should Scrutinise

- Whether `management_action_points(...)` should move into a separate service module once planning logic grows.
- Whether action-point thresholds need business configuration rather than hard-coded local rules.
- Whether the empty-upload validation should also include file size/type limits before production.
- Whether PDF output should be visually redesigned further using a branded report template.
- Whether browser checks should be converted into automated Playwright tests.

## Remaining External Items

The following are not local work and were not claimed complete:

- HMRC production filing approval and live filing.
- Companies House filing/submission access.
- Live bank feeds.
- Live payment provider integration.
- Public DNS/server deployment.
- Legal/commercial review.

## Conclusion

This final local hardening pass completed safer upload validation, action-oriented report generation, rendered report action points, focused tests, Django checks, migration checks, browser review and a final 119-test regression run.
