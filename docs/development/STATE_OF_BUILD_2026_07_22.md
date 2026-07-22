# LedgerHouse State of Build

Date: 2026-07-22

## Scope of this assessment

This report records the repository state found at the start of the current
build pass. It separates code that has been executed locally from code that
is only a local simulation of an external service. It does not treat an
earlier report or a source-code reading as proof of production readiness.

## Verified working locally

The following has executable local coverage and was reported as passing in
the latest local acceptance/hardening pass:

1. PostgreSQL-backed, tenant-scoped accounting ledger with journal balance,
   locked-period, VAT-lock and audit-log protections.
2. Client login, client portal, practice dashboard, client access restrictions
   and invitation/access workflow.
3. Evidence upload and storage for non-bank documents, CSV bank import and
   XLSX bank import.
4. Evidence review, ledger review, bank review, journal approvals, client
   questions and local client approvals.
5. Management CSV/PDF/PDF-pack exports, accounts-department pack and client
   data ZIP export.
6. Local sales, purchase, payment-run, fixed-asset, payroll/CIS, tax-estimate,
   month-close and statutory-readiness records.
7. Companies House public-data lookup, local scenario accounts generation,
   iXBRL generation/validation, test-submission recording, status polling and
   a production safety lock.
8. Local acceptance command and a full Django regression pass previously
   recorded as 149 tests passing.

## Partially built or deliberately simulated

1. `accounting/intake.py` classifies document uploads using filename/content
   keywords and extracts only simple text amounts. It is not OCR or a
   production invoice-recognition engine.
2. `accounting/open_banking.py:7` uses `MockOpenBankingClient`; the sync and
   reconciliation paths are testable, but there is no live bank provider
   connector.
3. `accounting/mtd.py:283` has `MockHMRCClient` for local submission tests.
   Real sandbox/production calls are separately implemented but require
   configured credentials and taxpayer authorisation.
4. `accounting/operations.py:437` creates an `EmailMock` notification event;
   no email delivery provider exists.
5. Companies House filing is kept in test mode until Companies House confirms
   the submitted gateway tests and authorises production use.

## Missing entirely

1. A root `README.md` that permits a clean developer to install, start, test,
   verify and stop the product without relying on historic chat context.
2. A local-only provider contract that makes it impossible for an operator to
   mistake test notifications or mock bank data for a live integration.
3. A dedicated operational timeline screen that aggregates finance-office
   actions from the immutable audit data in a client-safe, readable form.
4. A dedicated reproducibility command that performs migration, system-check,
   acceptance and regression verification in the documented order.

## Shortcut and placeholder inventory

These are recorded rather than silently removed, because some are intentional
local test doubles and must remain external boundaries until real credentials
and provider agreements are available.

| Location | Finding | Classification |
| --- | --- | --- |
| `accounting/intake.py:21-24` | Broad exception ignores non-decodable content during local classification. | Harden locally. |
| `accounting/open_banking.py:7-27` | `MockOpenBankingClient` returns fixed test transactions. | External-provider boundary. |
| `accounting/open_banking.py:92-97` | Missing matching journal is silently ignored. | Harden locally. |
| `accounting/mtd.py:283-405` | `MockHMRCClient` and mock VAT submission path. | External HMRC boundary. |
| `accounting/operations.py:435-443` | `EmailMock` event rather than delivery. | External email-provider boundary. |
| `accounting/middleware.py:39` | Fails closed by clearing tenant context if database reset fails. | Intentional defensive handling. |
| `accounting/tests/*` | Mock/dummy values are test fixtures. | Test-only, not product code. |
| root | No `README.md` exists. | Build defect. |

## Broken, untested or currently unverified paths

1. At assessment start, `ledgerhouse_web` was stopped, so no current runtime
   verification had yet been performed in this pass.
2. A fresh-machine install cannot be verified from the repository because the
   root README is absent.
3. Live bank synchronisation, real email delivery, HMRC live filing, Companies
   House production filing, payment collection, public DNS/TLS and production
   backup restoration require external services or approvals and are not
   claimed as locally complete.

## Ordered build backlog

1. Add a root README and a repeatable local verification command; prove it
   starts a stopped local stack and runs database/migration/acceptance checks.
2. Make the notification and open-banking provider boundaries explicit, with
   safe local implementations, actionable status and no silent matching loss.
3. Add a practice operations timeline based on immutable audit events with
   role-protected access and browser verification.
4. Harden evidence intake: typed extraction results, explicit confidence,
   deterministic amount selection and invalid-document outcomes.
5. Add local recurring-accounting schedules for accruals, prepayments and
   depreciation, with posting safeguards and closing-period exceptions.
6. Add a local accounting exception register that combines review, unmatched
   bank, approval, document and month-close blockers.
7. Add client-safe approval-pack preview and release history.
8. Add a local workload board with controlled status transitions and audit
   events.
9. Add a wider browser acceptance suite covering client, accountant and error
   journeys at desktop and narrow viewport widths.
10. Run clean-stack, migration, focused, acceptance, browser and full
    regression verification; update handover and assumptions documents.

## External blockers to preserve

- HMRC production approval, taxpayer/agent OAuth and live filing.
- Companies House review of test submissions and production gateway approval.
- A contracted bank-feed provider and bank-consent journey.
- An email provider, verified sending domain and delivery credentials.
- Payment provider account/webhook configuration.
- Public deployment, DNS, TLS and production backup/restore environment.
- Legal, privacy, insurance and client-data admission approvals.
