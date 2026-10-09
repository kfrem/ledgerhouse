# Accounts Production Workspace: Build and Verification Record

Date: 30 July 2026  
Scope: local LedgerHouse development informed by a read-only review of the Capium Accountant accounts-production area.

## What was built

LedgerHouse now has a practice-only **Accounts Production** workspace at:

`/practice/accounts-production/?company=<tenant UUID>`

It uses the existing LedgerHouse records as the sole source of truth. No duplicate accounting ledger, mocked report record, or new external integration was introduced.

The workspace provides:

1. A client production profile using the latest real statutory draft and Companies House test submission where those records exist.
2. An annual accounts register showing an internal reference, reporting period, accounts type, lifecycle, client approval state, latest Companies House test delivery state, and associated submission number.
3. A management pack register grouped by reporting period with real pack sections, approval state, lifecycle and audited release-event count.
4. An open-work queue driven by existing `AccountingTask` records, including practice owner, due date, priority and controlled state.
5. A recent control-event timeline drawn from immutable `AuditEvent` history.
6. Links back to existing report, Companies House, accounts-department and operations-timeline workspaces.
7. A direct production-file entry point from the existing practice client page.

## Capium comparison

The review showed that Capium's useful pattern is a formal register: accounts and report periods retain a reference, status, source trial balance and controlled delivery actions. LedgerHouse now carries that same operational principle while retaining its client portal, evidence intake, approval gate and test-filing controls.

LedgerHouse does not claim Capium-equivalent live external filing, email delivery, electronic signing, payroll or tax submission from this work. Those are separate provider/approval integrations.

## Files changed

- `accounting/production.py`
- `accounting/views.py`
- `ledgerhouse/urls.py`
- `templates/accounting/practice_accounts_production.html`
- `templates/accounting/practice_client_detail.html`
- `static/accounting/dashboard.css`
- `accounting/tests/test_accounts_production.py`

## Automated tests

Focused Docker suite:

```text
docker compose exec -T web python manage.py test \
  accounting.tests.test_accounts_production \
  accounting.tests.test_workflow_controls \
  accounting.tests.test_accounts_department_suite --verbosity 1

Ran 18 tests in 9.254s
OK
```

The focused suite verifies real-record assembly, submission status, approvals, management-pack register entries, open-task owner display, audit-event tenant isolation, rendered workspace content and practice-only access.

Clean full Docker regression:

```text
docker compose exec -T web python manage.py test --noinput --verbosity 1

Ran 192 tests in 75.863s
OK
```

Additional checks:

```text
docker compose exec -T web python manage.py check
System check identified no issues (0 silenced).

docker compose exec -T web python manage.py local_acceptance_suite --strict
All local acceptance checks passed.

docker compose exec -T web python manage.py local_production_rehearsal
All local production rehearsal checks passed.
```

The acceptance suite verified the client portal, practice dashboard, accounts-department page, management-report HTML, CSV, PDF, management pack, accounts-department pack, client data ZIP and no-HMRC handover ZIP. The rehearsal verified the active PostgreSQL backend, migration state, management-report context, exports and client data export.

## Visual check record

The in-app browser successfully rendered the existing LedgerHouse client portal at desktop width and a Capium Accountant accounts-production screen was reviewed visually. The new protected practice workspace could not be captured in that same session because the current local browser session was a client session, and its POST-only sign-out route rejected direct navigation; Browser Use then blocked further login-state manipulation. No browser restriction was bypassed.

The protected route and role boundary were tested by `AccountsProductionWorkspaceTests.test_client_cannot_open_practice_production_workspace`, and the page content was tested by the Django response test. A fresh in-app browser practice session remains the only outstanding visual check for this page.

## External boundaries

- Companies House XML Team acceptance remains external. Test submissions being `Pending` is not acceptance.
- HMRC production approval and live filing remain external.
- Email delivery, e-signing, payments, payroll submissions and bank-feed connections require their respective credentials, provider configuration and live verification.
