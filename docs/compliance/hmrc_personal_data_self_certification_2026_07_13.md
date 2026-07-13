# HMRC Personal Data Self-Certification Evidence

Date: 2026-07-13

Software: LedgerHouse / KAFS UK Accounting SaaS.

## Scope

This record supports the HMRC Developer Hub personal-data checklist answers for the production credentials request.

## Data Processed

LedgerHouse processes accounting and practice-management data needed to support client bookkeeping, VAT review, management reporting and HMRC VAT MTD workflows.

Expected data categories:

- Client company details and company contacts.
- Uploaded invoices, receipts, bank files, payroll files, spreadsheets, PDFs and supporting evidence.
- Bank transaction records imported from CSV/XLSX or future bank-feed providers.
- Accounting journals, VAT returns, VAT review decisions and management reports.
- HMRC OAuth tokens and VAT identifiers where a client authorises the software.
- User account details and audit/event records.
- Client support/advice requests submitted through the portal.

## UK GDPR Position

The current controlled product has a defensible basis to answer **Yes** to UK GDPR compliance for the HMRC checklist:

- Processing is limited to accounting, tax compliance, reporting and client support purposes.
- Lawful bases are expected to include contract, legal obligation and legitimate interests depending on the customer relationship and processing purpose.
- Customers authorise HMRC API access through OAuth before HMRC data is accessed.
- Access is restricted through Django authentication and application-level role/workflow separation.
- Tenant isolation and PostgreSQL row-level security behaviour are covered by tests.
- Secrets are excluded from Git through `.env` and local secret files.
- Uploaded source documents are treated as client evidence and surfaced through controlled client/practice workflows.
- Audit immutability and posting controls are covered by automated tests.
- Breach notification process is documented in `docs/compliance/hmrc_service_management_self_certification_2026_07_13.md`.

## Customer Notice

Before broad public launch, LedgerHouse should publish customer-facing Terms, Privacy Notice and Data Processing terms that explain:

- What data is processed.
- Why it is processed.
- The lawful basis for processing.
- Whether KAFS/LedgerHouse acts as controller, processor, or both depending on the workflow.
- How long data is retained.
- How customers can request correction, export or deletion where applicable.
- How HMRC authorisation can be revoked.

For the current controlled HMRC production credentials request, the internal policy basis and limited controlled user scope support the self-certification answer.

## Security And Access Controls

Implemented or prepared controls:

- Django authentication required for client/practice screens.
- Practice, HMRC and Companies House workbenches are restricted to staff users.
- CSRF protection on state-changing forms.
- Role-separated client portal and practice dashboard workflows.
- `TenantUserAccess` assigns non-staff client users to specific client companies.
- Client tenant switching and report download routes enforce assigned company access before showing or exporting data.
- Client/provider-switching data export is available as an authenticated ZIP download containing ledger CSVs, VAT records, bank transaction CSVs, client request CSVs, evidence indexes and uploaded evidence files.
- Tenant isolation/RLS test coverage across journals, VAT, bank transactions, evidence, reconciliations, client requests and bank feed connections.
- PostgreSQL row-level security policies use the current tenant session setting and are installed by migrations.
- `deploy/create_app_role.sql` defines a restricted `ledgerhouse_app` role with `NOBYPASSRLS` for production connections.
- `accounting.checks` warns if a non-debug deployment connects as a superuser or role that bypasses RLS.
- Local secrets excluded from source control.
- Reversible application-level encryption for stored HMRC OAuth access tokens, HMRC refresh tokens and bank consent tokens using `accounting.crypto.EncryptedTextField`.
- Existing token rows are rewritten by migration `accounting.0015_alter_bankfeedconnection_consent_token_and_more`.
- Tests read the raw database columns directly and verify encrypted `enc:` values are stored while model access returns the original token values.
- Docker/PostgreSQL runtime separation.
- Production deployment plan includes HTTPS reverse proxy, firewall, fail2ban and unattended security updates.
- HMRC credentials and tokens are configured through environment variables, not source code.
- Production deployments must set `FIELD_ENCRYPTION_KEY` to a Fernet key generated outside source control. If not set, the app still encrypts with a key derived from Django `SECRET_KEY`, but a separate production key is preferred for operational rotation.
- Customer data is encrypted in transit by HTTPS/TLS in the production deployment plan. Local development uses localhost HTTP only for controlled testing.

## Evidence

- `LOCAL_COMPLETION_REGISTER.md`
- `docs/testing/local_completion_pass_2026_07_13.md`
- `docs/testing/hmrc_vat_workflow.md`
- `docs/compliance/hmrc_accessibility_self_certification_2026_07_13.md`
- `docs/compliance/hmrc_service_management_self_certification_2026_07_13.md`
- `docs/compliance/hmrc_software_security_self_certification_2026_07_13.md`
- `accounting/crypto.py`
- `accounting/migrations/0015_alter_bankfeedconnection_consent_token_and_more.py`
- `accounting/migrations/0016_tenantuseraccess.py`
- `accounting/middleware.py`
- `accounting/reports.py`
- `deploy/create_app_role.sql`
- `accounting/tests/test_client_portal_workflows.py`
- `accounting/tests/test_audit.py`
- `accounting/tests/test_bank_import.py`
- `accounting/tests/test_evidence.py`
- `accounting/tests/test_kernel.py`
- `accounting/tests/test_reconciliation.py`
- `accounting/tests/test_hmrc_sandbox.py`
- `accounting/tests/test_phase2_3.py`
- Full suite latest result: `103 passed`.
- Encryption verification latest result: `accounting.tests.test_hmrc_sandbox accounting.tests.test_phase2_3` ran 27 tests OK on 2026-07-13.
- Full suite latest result after encryption: `97 tests OK` on 2026-07-13.
- Access-control verification latest result: `accounting.tests.test_client_portal_workflows` ran 20 tests OK on 2026-07-13.
- Full suite latest result after tenant-user access controls: `100 tests OK` on 2026-07-13.
- Data portability export verification: `accounting.tests.test_client_portal_workflows` ran 20 tests OK on 2026-07-13 and validates ZIP contents.
- Full suite latest result after data export: `100 tests OK` on 2026-07-13.
- Django system check after encryption: no issues.

## Production Follow-Up

Before accepting external paying clients, complete:

- Public Privacy Notice.
- Data Processing Agreement / SaaS terms.
- Retention and deletion schedule.
- Public security contact route.
- Hosted database, object storage and backup encryption settings should be confirmed in the final production hosting checklist before accepting external customer data.

These follow-ups improve launch maturity but do not prevent answering HMRC’s controlled self-certification question on the present evidence.
