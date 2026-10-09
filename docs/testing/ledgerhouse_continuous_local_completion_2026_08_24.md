# LedgerHouse continuous local completion report

**Date:** 24 August 2026  
**Scope:** LedgerHouse local build, integrity controls, automated regression,
Docker rebuild, backup rehearsal and rendered browser review. This report does
not claim HMRC production approval, a successful live tax filing, a successful
live payment, a delivered email or a successful live bank feed.

## Plain-English outcome

The known local LedgerHouse backlog was inspected and exercised again. Two
false-success risks and one mobile presentation failure were found and fixed:

1. HMRC authorisation is now tied to the browser session, is single-use, cannot
   redirect to an outside website, does not keep raw tokens in the browser
   session and does not display provider/network internals to the user.
2. A notification preview can no longer be marked as delivered without a real
   provider reference. Reviewing a preview leaves it queued.
3. Supplier payment runs now contain specific supplier bills. They require a
   payment reference, verify the run total and settle only their linked bills.
4. Customer receipts now have a proper receipt record, amount, date and unique
   bank/reference value. Partial payment works; duplicate references,
   overpayments and zero values are rejected.
5. The sales and purchase work areas now change into labelled, readable records
   on a phone instead of squeezing six columns into vertical text.

No known local-only defect remained open at the end of this pass. The remaining
items listed at the end need a provider, production environment, client action
or formal approval and cannot be honestly completed by local code alone.

## Files changed in this pass

- `accounting/mtd.py`
- `accounting/views.py`
- `accounting/notifications.py`
- `accounting/models.py`
- `accounting/operations.py`
- `accounting/workflow_controls.py`
- `accounting/migrations/0035_supplier_payment_run_integrity.py`
- `accounting/migrations/0036_sales_receipt_integrity.py`
- `accounting/tests/test_hmrc_sandbox.py`
- `accounting/tests/test_notifications.py`
- `accounting/tests/test_accounts_department_suite.py`
- `accounting/tests/test_workflow_controls.py`
- `templates/accounting/practice_accounts_department.html`
- `static/accounting/dashboard.css`
- `docs/testing/local_acceptance_suite_latest.md` (regenerated evidence)
- `docs/testing/commercial_readiness_rehearsal_latest.md` (regenerated evidence)

The repository was already heavily modified before this pass. Those existing
changes were preserved. No commit was made because committing the whole dirty
worktree would mix this work with changes from earlier work.

## Automated test evidence

### Baseline before corrections

- Full suite: **231 tests passed** in 83.145 seconds.
- Strict local acceptance: **all checks passed**, including all 8 accounts
  department phases, client portal, practice screens, report formats and ZIP
  exports.
- Commercial rehearsal: **6 synthetic businesses passed** evidence, banking,
  double entry, reporting, accounts-production and filing-safety checks.
- Backup restore rehearsal: passed.

### Focused correction tests

- HMRC sandbox and OAuth: **32 tests passed**.
- Notification and accounts-department controls: initial run found one missing
  test import; corrected run: **17 tests passed**.
- Payment and receipt workflow controls: **20 tests passed**.
- Additional payment/receipt control tests cover:
  - unmatched and replayed OAuth state;
  - external OAuth return address rejection;
  - missing/malformed HMRC token response;
  - provider network failure;
  - notification delivery evidence;
  - preview review without delivery status;
  - partial and full customer receipts;
  - overpayment and duplicate receipt rejection;
  - payment runs with no bills or mismatched totals;
  - settling linked bills only;
  - database rejection of cross-client payment links.

### Complete regression after corrections

- First final full suite: **243 tests passed** in 83.923 seconds.
- Second final full suite: **243 tests passed** in 73.792 seconds.
- Django model drift check: **no changes detected**.
- Django system check: **no issues**.
- Production-style Django security configuration check: **no issues** when
  production-only TLS, secret and debug settings were supplied.
- Python compile check: **passed**.
- Health endpoint: **HTTP 200**.

## Acceptance and data evidence

- Strict acceptance repeated after the corrections: **all checks passed**.
- Accounts department: **8 of 8 phases passed**.
- Verified routes and generated outputs:
  - client portal;
  - practice dashboard;
  - accounts-department workspace;
  - accounts-production workspace;
  - management report;
  - CSV report;
  - PDF report;
  - management pack PDF;
  - accounts-department pack PDF;
  - client data ZIP;
  - no-HMRC handover ZIP.
- Commercial rehearsal repeated for CareCo, CharityCo, ConsultCo, LogisticsCo,
  TechCo and TradeCo: **all checks passed**.
- Trial balance for every rehearsal business: **0.00**.
- External filing safety: **no false live submission records**.

## Database and backup evidence

- Migrations 0035 and 0036 applied successfully.
- New supplier-payment links and sales receipts have tenant ownership and
  PostgreSQL row-level security.
- Database triggers reject a bill or receipt linked to another client's record.
- Final backup:
  `backups/ledgerhouse-local-20260824-193914.zip`.
- Backup contents: **3,547 records**.
- Rollback-only restore rehearsal: **2,501 mutable records restored then rolled
  back; 1,046 immutable audit records deserialised and validated**.

## Docker evidence

- Final Docker image built successfully.
- Database container reported healthy.
- Web container was recreated and started.
- Final migration check reported no outstanding migrations.
- Final application check reported no issues.
- Final health request returned **HTTP 200**.

## Browser evidence

The actual rendered application was checked in the Codex in-app browser.

### Desktop

- `/practice/accounts-department/`: loaded successfully; receipt and supplier
  payment controls visible; no console warning or error.
- `/reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/`: report headings, figures,
  PDF, pack and CSV actions visible; no horizontal overflow; no console warning
  or error.

### Mobile (390 x 844)

- `/`: client portal loaded with usable navigation, company selector and
  primary actions; no horizontal overflow; no console warning or error.
- `/practice/accounts-department/`: receipt and supplier-payment inputs visible;
  six-column rows converted to one-column labelled records; no horizontal
  overflow; no console warning or error.
- A clean Docker rebuild was followed by the same mobile check. The page title,
  heading, receipt control and payment control were present and the corrected
  layout remained active.

## HMRC sandbox evidence (redacted)

- Application: LedgerHouse sandbox application.
- Endpoint: `GET /hello/application`.
- Result: **HTTP 200**.
- Timestamp: `2026-08-24T08:14:37.551447+00:00`.
- No client ID, secret, access token, refresh token, OTP or taxpayer data is in
  this report.
- The current code continues to fail closed: local preparation cannot create a
  provider receipt, accepted filing or accounting side effect without a real
  provider response.

## Remaining external blockers only

1. **HMRC production credentials:** Developer Hub still needs to issue the
   LedgerHouse production credential values for the approved/subscribed API.
2. **HMRC live authority and validation:** a real authorised taxpayer or agent,
   the correct production scopes, real fraud-prevention data and HMRC's live
   responses are required before any production filing can be claimed.
3. **Additional HMRC services:** Corporation Tax, PAYE/RTI, CIS, Income Tax MTD
   and Self Assessment require their applicable HMRC enrolment/approval,
   credentials and provider validation before their local preparation cases can
   become live submissions.
4. **Companies House live use:** real filings must use the approved live package
   and presenter configuration, a real company's authority and the live Gateway.
   The live service must not be used for testing.
5. **Email delivery:** a selected email provider, account, sending-domain setup
   and provider delivery references are required. LedgerHouse now refuses to
   turn a local preview into a delivered message.
6. **Payments and bank feeds:** provider accounts, client consent, production
   keys/certificates and real provider responses are required.
7. **Public operations:** final server secrets, restricted production database
   role, HTTPS/DNS verification, monitored off-site backup destination and a
   controlled deployment rehearsal are environment work, not local feature
   code.
8. **Commercial sign-off:** legal/privacy review and pilot-user acceptance must
   be performed by the responsible people; automated tests cannot replace them.

## Conclusion

LedgerHouse's currently known local build is internally consistent and passes
the repeated automated, acceptance, backup, Docker and browser checks described
above. That supports local testing and a controlled pilot preparation. It does
not, by itself, prove HMRC acceptance, Companies House acceptance, live email
delivery, live banking, live payment collection or production readiness.
