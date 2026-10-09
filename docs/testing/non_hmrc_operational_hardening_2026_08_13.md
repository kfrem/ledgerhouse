# LedgerHouse Non-HMRC Operational Hardening - 13 August 2026

## Scope

This pass continued local LedgerHouse development without using an HMRC live
credential, HMRC customer authority, paid provider, or live financial filing.
Capium was accessed only as a high-level product comparison reference. No
Capium customer records, payroll details, company data or credentials were
copied into LedgerHouse.

## Completed

### Evidence intake controls

- Reject unsafe filenames before they reach the evidence vault.
- Check the actual signatures of PDF, JPEG, PNG, WEBP and HEIC evidence files;
  the browser-supplied content type is not trusted.
- Check XLSX archives before parsing, including required workbook parts, member
  count and decompressed-size limits.
- Reject binary or non-UTF-8 CSV/text files before bank or evidence processing.
- Add a browser file-picker hint for the supported evidence formats. Server
  validation remains authoritative.

### Multi-client practice safety

- Corrected tenant selection for form posts. The selected `company` value is
  now considered by tenant middleware, but only after it is verified against
  the authenticated user's permitted client set.
- Added positive and negative tests proving an authorised POST selects the
  correct tenant and an unauthorised tenant ID is ignored.

### Payroll control workspace

- Added `/practice/payroll/` for practice staff.
- A validated UTF-8 payroll CSV can create a balanced local double-entry
  payroll journal and a payroll-period register record.
- Required columns are enforced: `Department`, `GrossPay`, `EmployerNI`,
  `EmployeeNI`, `PAYETax`, and `NetWages`.
- Gross pay must equal PAYE, employee NI and net wages; negative/non-numeric
  values fail with a row-specific error.
- Duplicate posting for the same payroll period is blocked. A ledger reversal
  review is required before replacement.
- Every successful payroll post adds an audit event.
- This workspace deliberately does not make RTI, pension or HMRC submissions.

### Responsive interface correction

- Desktop and mobile payroll screens were reviewed.
- The mobile check found horizontal page overflow. Shared responsive CSS was
  corrected and the repeat check found no horizontal overflow at 390px width.

## Files Changed

- `accounting/intake.py`
- `accounting/middleware.py`
- `accounting/payroll_cis.py`
- `accounting/views.py`
- `ledgerhouse/urls.py`
- `templates/accounting/client_portal.html`
- `templates/accounting/practice_payroll_review.html`
- `static/accounting/dashboard.css`
- `accounting/tests/test_intake_hardening.py`
- `accounting/tests/test_checks.py`
- `accounting/tests/test_payroll_workspace.py`

## Tests and Results

| Check | Result |
| --- | --- |
| Evidence intake and client workflow focus | Passed: 39 tests |
| Tenant selection and client workflow focus | Passed: 35 tests |
| Payroll, accounting-control and tenant focus | Passed: 16 tests |
| Complete Docker regression | Passed: 216 tests in 73.117 seconds |
| Desktop browser payroll route | Passed: rendered practice payroll controls and register |
| Mobile browser payroll route (390px) | Passed after correction: no horizontal overflow |
| Production Django check | Passed: no issues |
| Production internal health | Passed: `status: ok` |
| Production public health | Passed: HTTP 200 |
| Production protected payroll route | Passed: unauthenticated request redirects to sign in |

## Deployment

The live LedgerHouse container was rebuilt after a dated server-side backup was
created under `/srv/ledgerhouse/.codex-backups/20260813-before-payroll-and-tenant-selection`.
No database migration was required for the initial evidence, tenant and payroll
deployment described above. The later period-end pass is documented separately
below and includes migration `0033`.

## Period-End, Production and Operational Reporting Pass

### Completed

- Added a dedicated practice month-end workspace at `/practice/period-end/`.
- Added factual close controls for unreconciled bank transactions, unreviewed
  evidence, payroll journals, schedule postings, review sign-off and period
  locks.
- Added idempotent local accrual, prepayment and depreciation schedule posting.
  Re-running the same period cannot create duplicate routine journals.
- Added a controlled close action. It rejects incomplete periods, creates an
  immutable period lock only after all controls pass, and records an audit
  event with the closing user and dates.
- Added an explicit, auditable no-payroll declaration for a period. This is
  available only when payroll genuinely does not apply; it does not pretend a
  payroll journal was posted.
- Added controlled `Open -> In progress -> Done` task transitions in both
  practice workspaces. Invalid status jumps are rejected and logged.
- Added a visible approval-pack release panel. Only a client-approved pack with
  no previous release event can be released, and an empty state is shown when
  there is nothing eligible.
- Added month-end state and action points to management reporting.

### Tests and Evidence

| Check | Result |
| --- | --- |
| Period-end, production, accounts-department and workflow focus | Passed: 23 tests |
| Post-finalisation period-end, production and accounts-department focus | Passed: 21 tests |
| Full Docker regression after finalisation | Passed: 219 tests in 82.517 seconds |
| Migration validation | Passed: `makemigrations --check --dry-run` reported no changes |
| Local schema migration | Passed: `accounting.0033_monthendclose_payroll_not_applicable` applied |
| Local production-style Django check | Passed: no errors at error level; local development-only security warnings are expected because local Docker uses `DEBUG=True` |
| Browser: month-end route | Passed: all close-gate states, idempotent schedule form and no-payroll declaration rendered |
| Browser: accounts production route | Passed: controlled task actions and clear no-pack-release state rendered; no horizontal overflow at the tested desktop width |
| Live migration | Passed: `accounting.0033_monthendclose_payroll_not_applicable` confirmed applied |
| Live application check and internal health | Passed: no check errors and `status: ok` |
| Live public health | Passed: HTTP 200 |
| Live protected month-end route | Passed: HTTP 302 to sign in when unauthenticated |

### Live Deployment Notes

The period-end and production-control files were transferred to the existing
LedgerHouse service and the web container was rebuilt. The first verification
found that the migration file had not been applied; the application was not
treated as complete. It was then applied explicitly with the database schema
owner and re-verified before this report was updated.

No HMRC, Companies House, payment, bank-feed, payroll-provider or email
provider call was made in this pass. No filing record, provider receipt or
external acceptance was manufactured.

## External Boundaries Still Intact

- No HMRC live VAT return, RTI submission or customer OAuth action was made.
- No Companies House live submission was made.
- No payment, bank-feed, pension, email-provider or payroll-provider transport
  was simulated as successful.
- Off-server encrypted backup storage and a restore drill remain operational
  requirements before onboarding production client records.
