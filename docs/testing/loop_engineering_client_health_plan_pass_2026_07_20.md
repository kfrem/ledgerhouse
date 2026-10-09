# LedgerHouse Local Build Report - Client Accounts Health Plan

Date: 2026-07-20

Scope: local-only LedgerHouse / Full Accounts Dept development. No live HMRC filing, Companies House filing, payment provider action, DNS change, server deployment, or external service call was performed.

## Objective

Improve the client-facing product so it feels more like a useful accounts department and less like a technical bookkeeping/VAT screen. The specific local gap closed in this pass was: clients can see a plain-English plan explaining what records have been received, what still needs attention, what the accountant is doing, what approvals are waiting, and where reports can be downloaded.

## Built

- Added `_client_accounts_health_plan(...)` in `accounting/views.py`.
  - Builds a local five-part plan from current ledger, evidence, bank, approval and report data.
  - Uses plain-English labels:
    - Records received
    - Bank matching
    - Bookkeeping position
    - Approvals
    - Management pack
  - Adds a "Next best action" for each area.
  - Avoids live external dependencies.

- Wired the generated plan into the client portal context.

- Added a new client portal section in `templates/accounting/client_portal.html`.
  - Heading: `Accounts health plan`
  - Subheading: `What needs to happen next`
  - Shows each plan item as an actionable link to upload, support, approvals or reports.

- Added CSS in `static/accounting/dashboard.css`.
  - Full-width panel inside the client grid.
  - Three-column desktop layout.
  - Two-column tablet layout.
  - One-column mobile layout.
  - Uses existing 8px card radius and existing LedgerHouse visual style.

- Extended regression coverage in `accounting/tests/test_client_portal_workflows.py`.
  - The client portal test now creates realistic evidence, unmatched bank data and statutory approval data.
  - The test asserts the health-plan copy, statuses and next actions render.

## Review And Correction Loop

Initial implementation passed the focused unit test, but browser review found the rendered panel was too narrow when placed in the existing two-column client grid.

Correction 1:

- Changed `.accounts-health-plan` to span the full client grid row.
- First browser recheck showed the panel worked but five columns made each card too narrow.

Correction 2:

- Changed `.health-plan-list` from five columns to three columns on desktop.
- Added responsive rules so it becomes two columns at tablet width and one column at mobile width.

Correction 3:

- Fixed generated copy from a poor singular/plural phrase to:
  - `1 bookkeeping entry is recorded.`
  - `N bookkeeping entries are recorded.`

## Tests Run

Focused client portal test:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_portal_surfaces_plain_english_action_cards --noinput
```

Result: passed.

Related client/report workflow subset:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_login_flow_and_client_portal_render accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_can_review_local_approval_queue accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_can_view_management_report_in_app accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf --noinput
```

Result: 4 tests passed.

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

Result: 118 tests passed.

The full regression included the existing end-to-end verification across all six seeded demo tenants:

- CareCo Limited
- ConsultCo Consulting
- TradeCo Retail
- TechCo Software Ltd
- LogisticsCo Transport Ltd
- CharityCo Foundation

## Browser Review

Browser surface: Codex in-app browser.

URL reviewed:

```text
http://127.0.0.1:8000/?company=76168495-36f8-5eb6-9e25-fdce5c9213ef
```

Company reviewed: CareCo Limited.

Observed:

- Client portal loaded successfully.
- New `Accounts health plan` section rendered.
- Five plan items rendered.
- Each item included a status and `Next best action`.
- Final corrected desktop layout rendered as:
  - Section width: about 923px
  - Grid columns: three columns
  - Card width: about 287px
  - Card heights: about 216px to 236px

Browser issue found and corrected:

- The first browser review showed the section was too tall and narrow.
- The second review showed five desktop columns were too cramped.
- Final review confirmed the corrected three-column layout.

## Files Changed In This Pass

- `accounting/views.py`
- `templates/accounting/client_portal.html`
- `static/accounting/dashboard.css`
- `accounting/tests/test_client_portal_workflows.py`
- `docs/testing/loop_engineering_client_health_plan_pass_2026_07_20.md`

## What Another AI Should Scrutinise

- Whether `_client_accounts_health_plan(...)` should eventually move from `views.py` into a service/operations module if more planning logic is added.
- Whether the five plan items are the right client-facing categories for a paid SaaS product.
- Whether the copy should be made even simpler for non-accountants.
- Whether browser tests should be formalised into automated Playwright tests instead of being documented manual browser checks.
- Whether the client health plan should include direct links to specific outstanding documents or bank lines in a later pass.

## External Items Not Attempted

- HMRC production filing approval.
- Companies House filing/submission route.
- Live bank feeds.
- Live payment provider integration.
- Public DNS/server deployment.
- Legal/commercial review.

## Conclusion

This pass completed a local client-facing product improvement, reviewed it in the browser, corrected layout and copy issues found during review, and verified the final state with focused tests, Django checks, migration checks and the full 118-test regression suite.
