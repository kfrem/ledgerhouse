# LedgerHouse Local Accounts Department - Operating Action Test

Date: 17 July 2026

## Scope

This pass verifies that the local accounts department screen is not just a static checklist. It confirms that the practice user can operate the local finance-office records from the rendered browser screen before any live server, HMRC filing, Companies House filing, payment provider, or email gateway is used.

Test URL:

- `http://127.0.0.1:8000/practice/accounts-department/`

Login used:

- `admin`

## What Was Built In This Pass

The local accounts department screen now supports practice-side operating actions:

- Rebuild or refresh the local phase 1 to 8 sample operating records.
- Mark a sales invoice as paid.
- Approve a purchase bill.
- Mark a supplier payment run as paid.
- Complete an accounting task.
- Mark a mock client notification as sent.
- Download a dedicated accounts department PDF pack from the same local operating records.
- Include the accounts-department operating records in the client ZIP data export.

The page also presents the client finance-office view in business language:

- Sales ledger and credit control.
- Purchase ledger and supplier payment runs.
- Month-end close and fixed assets.
- Payroll, PAYE, CIS and corporation tax estimates.
- Statutory accounts draft and filing readiness.
- Practice tasks and mock client notifications.
- Local phase evidence for phases 1 to 8.

## Automated Test Evidence

Commands run inside Docker:

```text
docker compose exec -T web python manage.py test accounting.tests.test_accounts_department_suite
```

Result:

```text
Found 5 test(s).
Ran 5 tests in 2.405s
OK
```

Command:

```text
docker compose exec -T web python manage.py check
```

Result:

```text
System check identified no issues (0 silenced).
```

Command:

```text
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

```text
No changes detected
```

Command:

```text
docker compose exec -T web python manage.py test
```

Result:

```text
Found 116 test(s).
Ran 116 tests in 98.789s
OK
```

## Browser Test Evidence

An authenticated browser smoke test was run against the rendered local app using the actual Chrome executable on this machine.

Actions completed through the browser:

- Signed in as `admin`.
- Opened `/practice/accounts-department/`.
- Clicked `Build local suite`.
- Clicked `Mark paid`.
- Clicked `Approve`.
- Clicked `Mark run paid`.
- Clicked `Complete task`.
- Clicked `Mark sent`.

Browser assertions passed:

- Page title was `LedgerHouse | Accounts department suite`.
- The page showed `Run the client finance office from one place`.
- Sales ledger panel was present.
- Supplier/payment run panel was present.
- Month-end panel was present.
- PAYE/CIS/corporation tax panel was present.
- Statutory accounts panel was present.
- Tasks and mock notifications panel was present.
- Paid and sent statuses appeared after actions.
- Raw internal enum labels such as `ClientApproval`, `AwaitingApproval`, `InProgress`, and `RequiresReview` did not appear in the rendered page text.
- The `Accounts pack` link was visible on the rendered page.
- The browser downloaded `CareCo Limited-accounts-department-pack.pdf`.
- The downloaded file started with `%PDF` and was 6,590 bytes in the browser smoke test.
- The client portal `Data export` link downloaded `CareCo Limited-data-export.zip`.
- The downloaded ZIP had a valid ZIP signature and was 8,486 bytes in the browser smoke test.

Accounts-department CSV files now included in the data export:

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

Screenshot captured:

- `docs/testing/accounts_department_verified_ui_2026_07_17.png`

## Local-Only Boundary

This confirms the local workflow and screen behaviour. It does not prove live external submission because the following remain intentionally gated:

- HMRC production/live filing approval.
- Companies House live accounts submission credentials and gateway route.
- Live payment provider keys.
- Live email delivery credentials.
- Public server/DNS deployment.

The local code is structured so those gateways can be connected later without changing the core accounts-department records and workflow tested here.
