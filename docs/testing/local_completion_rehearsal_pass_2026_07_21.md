# LedgerHouse Local Completion Rehearsal Pass

Date: 2026-07-21

Scope: local-only build completion. No live HMRC, Companies House filing, bank feed, payment provider, DNS, server deployment, payment, or legal/commercial action was performed.

## Objective

Complete the remaining buildable local work without external information, then test, review and document it.

## Completed

### 1. Local Production Rehearsal Command

Added:

```text
accounting/management/commands/local_production_rehearsal.py
```

The command performs locally-checkable rehearsal checks:

- Django system check.
- Migration state check.
- Database backend check.
- Tenant data availability check.
- Management report context generation.
- CSV report export generation.
- PDF report and management pack export generation.
- Client data export ZIP generation.

It does not call external services and does not mutate production-like data.

Manual command result:

```powershell
docker compose exec -T web python manage.py local_production_rehearsal
```

Result:

- All local production rehearsal checks passed.
- Active backend: PostgreSQL.
- Tenant records available: 6.
- CareCo report context generated with 6 action points.
- CSV report generated.
- PDF reports generated.
- Data export ZIP generated with 36 files.

### 2. Test Coverage For Rehearsal

Extended:

```text
accounting/tests/test_client_portal_workflows.py
```

Added test:

```text
test_local_production_rehearsal_command_passes_local_checks
```

The test proves the rehearsal command reports all expected local checks as passing.

### 3. Previously Completed Local Hardening Reverified

The full suite also reverified:

- Empty upload rejection.
- Management report action points.
- CSV/PDF/pack exports.
- HTML management report action-point section.
- Client portal, approvals, reports, evidence, banking and practice workflows already covered by the regression suite.

## Tests Run

Focused rehearsal test:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_local_production_rehearsal_command_passes_local_checks --noinput
```

Result: passed.

Focused local-hardening group:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_local_production_rehearsal_command_passes_local_checks accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_production_readiness_command_reports_local_blockers accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_empty_upload_is_rejected_before_intake accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_can_view_management_report_in_app --noinput
```

Result: 5 tests passed.

Django checks:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

- System check passed with no issues.
- No migration changes detected.

Full regression:

```powershell
docker compose exec -T web python manage.py test --noinput
```

Result:

- 120 tests passed.
- Existing end-to-end verification across all six seeded demo tenants passed.

Demo tenants verified by the suite:

- CareCo Limited
- ConsultCo Consulting
- TradeCo Retail
- TechCo Software Ltd
- LogisticsCo Transport Ltd
- CharityCo Foundation

## Browser Review

Browser: Codex in-app browser.

URL reviewed:

```text
http://127.0.0.1:8000/reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/
```

Company: CareCo Limited.

Verified:

- Page title: `LedgerHouse | Management report`.
- User was already authenticated locally.
- `Action points` section rendered.
- `What should happen next` rendered.
- `Generated locally` rendered.
- 6 action cards rendered from local data.

Observed action points included:

- Evidence review.
- Bank matching.
- Client question response.
- Debtor review.
- Creditor payment planning.
- Cash runway review.

## Files Changed In This Pass

- `accounting/management/commands/local_production_rehearsal.py`
- `accounting/tests/test_client_portal_workflows.py`
- `docs/testing/local_completion_rehearsal_pass_2026_07_21.md`

## Current Local Status

Local build status after this pass:

- Rehearsal command: complete.
- Focused tests: passing.
- System checks: passing.
- Migration dry-run: clean.
- Full regression: 120 tests passing.
- Browser report review: passing.

## Worktree Note

The repository still contains a large dirty worktree from earlier LedgerHouse build passes. I did not stage, commit, delete or reorganise files in this pass because doing that safely requires a separate review/commit pass to avoid mixing unrelated previous work.

## Remaining Items That Are Not Local

The following cannot be completed without external access, approval, live setup or business sign-off:

- HMRC production filing approval and live filing.
- Companies House filing/submission access.
- Live bank feeds.
- Live payment provider setup.
- Public DNS/server deployment.
- Legal/commercial review.

## Conclusion

This pass completed the final local production rehearsal capability, verified it directly, added regression coverage, reran checks and the full 120-test suite, and browser-reviewed the rendered management report action points.
