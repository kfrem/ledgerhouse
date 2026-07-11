# LedgerHouse Phase 1, 2, and 3 — Technical Audit & Handoff Document

This document provides a comprehensive technical walkthrough of the entire LedgerHouse codebase, detailing the database triggers, RLS isolation policies, Open Banking sync client, MTD filing module, Payroll and CIS integrations, and areas for verification/improvement.

---

## 1. Tech Stack & Environment
*   **Framework**: Django 5.2.16 (Python 3.13)
*   **Database**: PostgreSQL 16
*   **Security & Isolation**: PostgreSQL Row-Level Security (RLS) policies enforced for `ledger_tenant_role`.
*   **Integrity Rules**: Enforced via PostgreSQL PL/pgSQL database triggers.

---

## 2. Codebase Layout & Key Files

The codebase is organized as follows:

*   [accounting/admin.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/admin.py): Registers all 15 models (including `BankFeedConnection`) in the Django admin panel.
*   [accounting/models.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/models.py): Declares schemas, database triggers, and model relations.
*   [accounting/open_banking.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/open_banking.py): Open Banking sync client with mock aggregator transaction sync.
*   [accounting/mtd.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/mtd.py): HMRC MTD for VAT submission engine (9-box mapping and mock portal).
*   [accounting/payroll_cis.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/payroll_cis.py): Parses payroll journals, verifies double-entry balance, and calculates subcontractor CIS tax splits.
*   [accounting/console.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/console.py): Cross-tenant accountant partner console aggregator.
*   [accounting/audit.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/audit.py): Trial Balance reports, period locking, audit checks.
*   [accounting/bank_import.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/bank_import.py): CSV parser with SHA-256 deduplication and FITID checks.
*   [accounting/middleware.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/middleware.py): Tenant context manager setting `app.current_tenant_id`.
*   [accounting/reconciliation.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/reconciliation.py): Bank clearing matching rules and ledger balance audits.
*   [accounting/reversals.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/reversals.py): Period-shifting journal reversal engine.
*   [accounting/vat.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/vat.py): Priority VAT rate lookup and control reports.
*   **Fixtures & Seeding**:
    *   [fixtures/factory.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/fixtures/factory.py): Original CareCo, ConsultCo, TradeCo synthetic generator.
    *   [fixtures/new_companies.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/fixtures/new_companies.py): Seeder script for TechCo, LogisticsCo, CharityCo.
    *   [management/commands/seed_db.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/management/commands/seed_db.py): Seeder command populating all 6 tenants and reconciling them.
*   **Test Suites**:
    *   [tests/test_phase2_3.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/tests/test_phase2_3.py): Phase 2 & 3 sync and statutory tests.
    *   [tests/test_end_to_end.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/accounting/tests/test_end_to_end.py): Unified end-to-end stage verification across all 6 clients (including Phase 2 & 3 integrations).

---

## 3. Core Accounting Mechanics

### 1. Integrity & Isolation (PostgreSQL Triggers & RLS)
*   **Double-Entry Balancing**: Trigger `check_journal_balance` on the table `accounting_journalline`. Ensures total debits equal total credits.
*   **Closed Accounting Periods**: Trigger `check_period_not_closed` blocks all mutations in closed `AccountingPeriod` intervals.
*   **Tenant Isolation**: PostgreSQL Row-Level Security policies block cross-tenant database operations based on session parameters (`app.current_tenant_id`).

### 2. Bank Synchronization & Clearing (Phase 2 & 3)
*   **Open Banking Engine**: Syncs with bank institutions, logs session references, and runs the matching engine.
*   **HMRC MTD Filing**: Extracts 9-box VAT values directly from ledger lines and posts to mock HMRC services.
*   **Payroll & CIS Withholding**: Dynamically imports payroll csv columns and splits subcontractor payments into expense debits, CIS tax liabilities, and Net Aged Creditors.

---

## 4. Verification & Commands

All database setups are containerized. To run them, execute the following commands in the workspace root:

1.  **Launch Database & Web Services**:
    ```bash
    docker compose up -d
    ```
2.  **Apply Django Migrations**:
    ```bash
    docker compose run --rm web python manage.py migrate
    ```
3.  **Seed Database (All 6 Clients)**:
    ```bash
    docker compose run --rm web python manage.py seed_db
    ```
4.  **Run All Tests (47/47 passing on PostgreSQL)**:
    ```bash
    docker compose run --rm web pytest
    ```

---

## 5. Identified Gaps, Shortcuts, and Improvement Opportunities

When reviewing this codebase for production readiness, prioritize the following areas:

### 1. SQLite Fallbacks in Test Suites
*   **Context**: Django's unit tests run on SQLite locally by default, but RLS policies and PL/pgSQL triggers are PostgreSQL-specific.
*   **Shortcut**: In test files (e.g. `test_end_to_end.py`), we check `self.is_postgres`. If `False`, tests manually simulate triggers (e.g. manually setting journal status to `'RequiresReview'` or `'Posted'`).
*   **Improvement**: Configure local testing to always run on PostgreSQL (e.g., using a local test database container) to avoid maintaining fallback mocks.

### 2. Binary Storage for Documents
*   **Context**: `EvidenceDocument.file_content` is stored as a `BinaryField` in the PostgreSQL database.
*   **Gap**: High document volumes will inflate database backups and slow down queries.
*   **Improvement**: Move document storage to an external object store (e.g., AWS S3, Google Cloud Storage) and save only the file URLs in the database.

### 3. High Volume Performance
*   **Context**: The reconciliation engine loops through transactions sequentially and posts balanced journals row-by-row.
*   **Opportunity**: Implement bulk matching algorithms or batch journal creations to scale up to tens of thousands of transactions.

### 4. Advanced Bank Matching
*   **Context**: The engine assumes a simple 1-to-1 match between a bank transaction and a ledger journal.
*   **Gap**: It does not handle 1-to-many matches (one statement line paying multiple invoices) or write-off tolerances for minor cash discrepancies.
*   **Improvement**: Add split payment allocations and write-off thresholds.

### 5. Multi-Currency Operations
*   **Context**: Supported in metadata, but the core double-entry engine assumes a single functional currency (GBP).
*   **Opportunity**: Introduce currency exchange rate tracking and automatic unrealized/realized gain/loss postings.
