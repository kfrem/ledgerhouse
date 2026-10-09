# LedgerHouse Local Build Report - Banking Rules and Document Intelligence

Date: 2026-07-19

Scope: local-only development pass for LedgerHouse / Full Accounts Dept. No live HMRC, Companies House, payment provider, DNS, or production server actions were performed.

## Completed Locally

- Added bank-rule suggestions to the practice banking review queue.
  - Unmatched bank lines are now checked against active `BankRule` records.
  - Matching lines display the suggested rule, account code, and confidence on `/practice/banking/`.
  - Posting a matched expense bank line now uses the suggested nominal account instead of the default expense code.
  - Journal descriptions now record when a bank rule was used.

- Improved document intelligence on evidence review.
  - Evidence analysis now applies active `DocumentIntelligenceRule` records before falling back to generic filename/content inference.
  - A matching rule can set the document category and suggested account code.
  - Existing amount, VAT, supplier/customer, and date extraction continue to run locally.
  - The audit trail records local evidence-analysis actions.

- Updated the banking review UI.
  - Reworded the navigation from VAT-only language to broader compliance language.
  - Reworded the admin fallback link as system records.
  - Added visible account suggestion text for each unmatched bank line.

- Added focused regression coverage.
  - Bank review test now proves that a rule-matched bank line displays the suggested account and posts to that account.
  - Added a document-intelligence rule test proving a fuel receipt is analysed into category `Receipt`, account `6100`, gross `72.00`, and VAT `12.00`.

## Commands Run

Focused tests:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_practice_can_review_unmatched_bank_lines_in_app accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_document_intelligence_rule_populates_review_suggestions accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_practice_can_review_evidence_uploads_in_app --noinput
```

Result: 3 tests passed.

Framework checks:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result: Django system check passed with no issues. No migration changes detected.

Full regression:

```powershell
docker compose exec -T web python manage.py test --noinput
```

Result: 118 tests passed. The suite included the existing end-to-end verification across 6 demo tenants.

## Browser Checks

Browser surface: Codex in-app browser.

Local login:

- URL: `http://127.0.0.1:8000/login/`
- Credentials used: `admin` / `admin2`
- Result: login succeeded and redirected to the local client portal.

Banking review:

- URL: `http://127.0.0.1:8000/practice/banking/?company=76168495-36f8-5eb6-9e25-fdce5c9213ef`
- Demo line: `Browser software subscription`
- Verified visible text:
  - `Suggested by Browser software rule`
  - `account 6200`
  - `Browser software subscription`
- Result: passed.

Evidence review:

- URL: `http://127.0.0.1:8000/practice/evidence/?company=76168495-36f8-5eb6-9e25-fdce5c9213ef`
- Demo evidence: `browser-fuel-receipt.txt`
- Action: clicked `Analyse` from the rendered evidence row.
- Verified rendered form values:
  - Category: `Receipt`
  - Supplier/customer: `Browser Fuel`
  - Gross: `72.00`
  - VAT: `12.00`
  - Suggested account: `6100`
  - Note: `Local document intelligence populated suggested fields.`
- Result: passed.

## Remaining External Blocks

These were intentionally not attempted in this local-only pass:

- HMRC production approval and live filing.
- Companies House filing/submission routes requiring external access or approval.
- Live payment provider setup and webhooks.
- DNS/server deployment verification.
- Legal review and commercial sign-off.

## Conclusion

This pass completed and verified a local improvement to accountant-side bank review and evidence/document intelligence. The work passed focused tests, Django checks, migration checks, full regression, and rendered browser checks.
