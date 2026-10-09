# LedgerHouse Local Phase 1-8 Accounts Department Pass

Date: 2026-07-16  
Environment: local Docker application at `http://127.0.0.1:8000/`  
Server deployment: not used  
External API calls: not used for the new local suite

## Objective

Build the local accounts department core across phases 1 to 8 without waiting for HMRC, Companies House, payment-provider, legal or production-server authorisations.

## What Was Built

### Phase 1: Core Operating Ledgers

Added local models and workflow evidence for:

- sales invoices
- purchase bills
- credit control actions
- supplier payment runs

The local builder creates overdue, paid, approved and awaiting-approval examples so debtor, creditor, credit-control and payment-run workflows can be tested.

### Phase 2: Month-End Accounts Department

Added local models and workflow evidence for:

- month-end close file
- bank reconciled flag
- accruals posted flag
- prepayments posted flag
- depreciation posted flag
- payroll posted flag
- reviewer sign-off
- fixed asset register and net book value

### Phase 3: Payroll, CIS and Tax Workflows

Added local models and workflow evidence for:

- payroll summary
- PAYE
- employee NI
- employer NI
- pension
- CIS deductions
- payroll journal posted status
- corporation tax estimate

### Phase 4: Statutory Accounts Preparation

Added local statutory accounts draft model covering:

- accounts type
- directors report readiness
- balance sheet readiness
- notes readiness
- client approval
- iXBRL readiness boundary

iXBRL remains deliberately false in the local builder because Companies House XML Gateway filing is a separate future filing engine.

### Phase 5: Client/Practice Collaboration

Added local models and workflow evidence for:

- accounting tasks
- task phase
- task owner
- priority
- status
- mock notification events

### Phase 6: Permissions and SaaS Controls

The new accounts department suite is practice-only. Tests confirm a client user cannot access it.

### Phase 7: Reports and Packs

The suite is integrated with the existing local report/export foundation. The phase snapshot confirms reports and packs remain locally available while the new operational records exist.

### Phase 8: Local Filing Readiness

The local statutory accounts draft exists and is tracked as filing readiness evidence. Live Companies House and HMRC filing remain externally gated and are not falsely enabled.

## Files Added Or Changed

- `accounting/models.py`
  - added local operational models for sales, purchases, credit control, supplier payments, month-end close, fixed assets, payroll, corporation tax, statutory accounts drafts, tasks and notification events
- `accounting/operations.py`
  - added `build_local_accounts_department_suite`
  - added `accounts_department_snapshot`
- `accounting/views.py`
  - added practice accounts department suite view
- `ledgerhouse/urls.py`
  - added `/practice/accounts-department/`
- `templates/accounting/practice_accounts_department.html`
  - added eight-phase local suite screen
- `templates/accounting/dashboard.html`
  - added navigation into the accounts department suite
- `accounting/admin.py`
  - registered new local operating records for inspection
- `accounting/tests/test_accounts_department_suite.py`
  - added focused tests for the new suite
- `accounting/migrations/0019_accountingtask_corporationtaxestimate_fixedasset_and_more.py`
  - added database tables for the local suite

## Tests Run

### System Check

Command:

```powershell
docker compose exec -T web python manage.py check
```

Result:

```text
System check identified no issues (0 silenced).
```

### Migration Dry-Run

Command:

```powershell
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

```text
No changes detected
```

### Migration Applied Locally

Command:

```powershell
docker compose exec -T web python manage.py migrate
```

Result:

```text
Applying accounting.0019_accountingtask_corporationtaxestimate_fixedasset_and_more... OK
```

### New Focused Suite Tests

Command:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_accounts_department_suite
```

Result:

```text
Found 4 test(s).
Ran 4 tests in 1.763s
OK
```

### Existing Client/Practice Workflow Tests

Command:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows
```

Result:

```text
Found 27 test(s).
Ran 27 tests in 20.308s
OK
```

### Companies House Boundary Tests

Command:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_companies_house
```

Result:

```text
Found 6 test(s).
Ran 6 tests in 1.393s
OK
```

### Full Test Suite

Command:

```powershell
docker compose exec -T web python manage.py test
```

Result:

```text
Found 113 test(s).
Ran 113 tests in 51.600s
OK
```

Expected local warning:

```text
accounting.W001 Database 'default' connects as a superuser or BYPASSRLS role.
```

This remains a production-only hardening gate.

## Browser Smoke Test

Browser: installed Chrome at `C:/Program Files/Google/Chrome/Application/chrome.exe`

Steps:

1. Logged into `http://127.0.0.1:8000/login/` as `admin / admin2`.
2. Opened `/practice/accounts-department/`.
3. Clicked `Build local suite`.
4. Confirmed the page rendered the eight local phases.

Browser assertions passed:

- Accounts department suite
- Core operating ledgers
- Month-end accounts department
- Payroll, CIS and tax workflows
- Statutory accounts preparation
- Client/practice collaboration
- Permissions and SaaS controls
- Reports and packs
- Local filing readiness
- `8 / 8 phases`

## Important Boundary

This pass completes a local operational suite for the eight phases. It does not mean real-world live filing, live payroll submission, live payments, legal sign-off or production deployment are complete. Those remain separate external or production gates.

The app now has local working records and tests across the eight phase areas, so development can continue from actual operating modules rather than from a list of intentions.
