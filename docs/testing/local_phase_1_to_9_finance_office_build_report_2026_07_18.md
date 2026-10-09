# LedgerHouse Local Phase 1 to 9 Finance Office Build Report

Date: 18 July 2026

## Objective

Build, test, correct and retest the next local-only finance-office capabilities for LedgerHouse without relying on live HMRC, Companies House, bank feeds, payment providers, email providers or public server deployment.

The target scope was:

1. Full sales workflow foundation.
2. Full purchase workflow foundation.
3. Banking depth.
4. Accounting period controls.
5. Management reporting pack depth.
6. Client portal/report export continuity.
7. Practice workflow visibility.
8. Document intelligence foundation.
9. Test evidence and repeat verification.

## What Was Built

### 1. Sales Workflow Foundation

Added `SalesQuote` records to support quote-to-invoice workflow tracking.

Local build now creates:

- `LH-Q-0001` accepted quote.
- Link from quote to the local sales invoice workflow.
- CSV export in `sales_quotes.csv`.
- PDF display in the accounts department pack.
- On-screen display in the accounts department workspace.

### 2. Purchase Workflow Foundation

Added `PurchaseOrder` records to support purchase order to supplier bill tracking.

Local build now creates:

- `LH-PO-0001` approved/billed purchase order.
- Link from purchase order to supplier bill.
- CSV export in `purchase_orders.csv`.
- PDF display in the accounts department pack.
- On-screen display in the accounts department workspace.

### 3. Banking Depth

Added `BankRule` records to support local bank-rule and reconciliation-intelligence setup.

Local build now creates:

- `Software subscriptions` bank rule.
- Match text: `SOFTWARE VENDOR`.
- Suggested nominal account: `6200`.
- Confidence score.
- CSV export in `bank_rules.csv`.
- PDF display in the accounts department pack.
- On-screen display in the accounts department workspace.

### 4. Accounting Period Controls

Added `AccountingPeriodLock` records to support local period lock/reopen control.

Local build now creates:

- Closed period lock for the local quarter period.
- Lock owner and reason.
- CSV export in `accounting_period_locks.csv`.
- PDF display in the accounts department pack.
- On-screen display in the accounts department workspace.

### 5. Management Reporting Pack Depth

Added `ManagementPackSection` records to support local commentary/review sections.

Local build now creates:

- `Director commentary` section.
- Reviewed status.
- Owner tracking.
- CSV export in `management_pack_sections.csv`.
- PDF display in the accounts department pack.
- On-screen display in the accounts department workspace.

### 6. Client Portal And Export Continuity

The existing client data export now includes the new finance-office records as CSV files. The client portal `Data export` link was browser-tested after the change.

New files included in ZIP export:

- `sales_quotes.csv`
- `purchase_orders.csv`
- `bank_rules.csv`
- `accounting_period_locks.csv`
- `management_pack_sections.csv`

Existing accounts-department files remain included:

- `sales_invoices.csv`
- `purchase_bills.csv`
- `supplier_payment_runs.csv`
- `month_end_closes.csv`
- `fixed_assets.csv`
- `payroll_summaries.csv`
- `corporation_tax_estimates.csv`
- `statutory_accounts_drafts.csv`
- `accounting_tasks.csv`
- `notification_events.csv`

### 7. Practice Workflow Visibility

The practice accounts-department screen now shows the expanded local workflow controls:

- Sales quote records.
- Purchase order records.
- Bank rule records.
- Period lock records.
- Management commentary records.
- Document intelligence rules.

The screen still includes the existing practice actions:

- Build local suite.
- Mark sales invoice paid.
- Approve purchase bill.
- Mark supplier payment run paid.
- Complete accounting task.
- Mark mock notification sent.
- Download accounts department PDF pack.

### 8. Document Intelligence Foundation

Added `DocumentIntelligenceRule` records to support local document classification rules.

Local build now creates:

- `Supplier invoice detector`.
- Keyword: `invoice`.
- Document category: `PurchaseInvoice`.
- Suggested nominal account: `6000`.
- Confidence score.
- CSV export in `document_intelligence_rules.csv`.
- PDF display in the accounts department pack.
- On-screen display in the accounts department workspace.

### 9. Test Evidence And Repeat Verification

Added and updated automated assertions for:

- Database records created by the local build.
- Accounts-department snapshot counts.
- Rendered screen content.
- PDF pack download.
- ZIP export content.
- Existing client export/report path.

## Files Changed

- `accounting/models.py`
- `accounting/operations.py`
- `accounting/reports.py`
- `accounting/views.py`
- `templates/accounting/practice_accounts_department.html`
- `accounting/tests/test_accounts_department_suite.py`
- `accounting/tests/test_client_portal_workflows.py`
- `accounting/migrations/0020_accountingperiodlock_bankrule_and_more.py`

## Test Passes Completed

### Migration

Command:

```text
docker compose exec -T web python manage.py makemigrations accounting
```

Result:

```text
Created accounting/migrations/0020_accountingperiodlock_bankrule_and_more.py
```

Command:

```text
docker compose exec -T web python manage.py migrate
```

Result:

```text
Applying accounting.0020_accountingperiodlock_bankrule_and_more... OK
```

### Focused Accounts Department Tests

Command:

```text
docker compose exec -T web python manage.py test accounting.tests.test_accounts_department_suite
```

Result:

```text
Found 7 test(s).
Ran 7 tests in 2.885s
OK
```

### Focused Client Export Test

Command:

```text
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf
```

Result:

```text
Found 1 test(s).
Ran 1 test in 1.759s
OK
```

### Django System Check

Command:

```text
docker compose exec -T web python manage.py check
```

Result:

```text
System check identified no issues (0 silenced).
```

### Migration Drift Check

Command:

```text
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

```text
No changes detected
```

### Full Regression Suite

Command:

```text
docker compose exec -T web python manage.py test
```

Result:

```text
Found 116 test(s).
Ran 116 tests in 107.995s
OK
```

The full suite also completed the six-tenant end-to-end verification:

```text
E2E verification of all 6 stages across 6 tenants successfully completed!
```

## Browser Verification

### Rendered Accounts Department Screen

Browser smoke test logged in as `admin`, opened the rendered accounts-department page, built the local suite and confirmed the following were visible:

- `LH-Q-0001`
- `LH-PO-0001`
- `Software subscriptions`
- `Period lock`
- `Director commentary`
- `Supplier invoice detector`
- `8 / 8`
- `Accounts pack` link

Result:

```text
errors: []
```

### PDF Download

Browser download check:

```text
File: CareCo Limited-accounts-department-pack.pdf
Header: %PDF
Size: 8,972 bytes
```

### ZIP Download

Browser download check:

```text
File: CareCo Limited-data-export.zip
Signature: PK
Size: 10,150 bytes
```

## Corrections Made During Testing

- A previous test command used the wrong test method name for the client export test. The correct method was located and rerun:
  `ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf`.
- Report/export patches were reapplied in smaller chunks where file context had moved from prior work.
- The web container was restarted after migration so the local rendered app used the new models.

## External Boundaries Still Not Claimed

This build is local-only. It does not claim the following are live-complete:

- HMRC production filing.
- Companies House live accounts submission.
- Live bank feed connection.
- Live payment collection.
- Live email sending.
- Public deployment/DNS/HTTPS.
- External legal/commercial approval.

## Conclusion

The local finance-office workflow has moved beyond invoices, bills and task display. It now includes local foundations for quotes, purchase orders, bank rules, period locks, management commentary and document-intelligence rules, with screen visibility, PDF pack output, ZIP export output and automated tests.

The local build passed focused tests, migration checks, full regression testing and browser download verification.
