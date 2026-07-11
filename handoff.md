# LedgerHouse Phase 1 — Technical Audit & Handoff Document

This document provides a comprehensive overview of the work completed during Phase 1 of LedgerHouse, detailing the technical architecture, implemented files, testing patterns, and areas for improvement/gaps.

---

## 1. Project Overview & Tech Stack

LedgerHouse is a multi-tenant, accountant-supervised finance operations platform designed with high-fidelity control, auditability, and data security at the database layer.

*   **Framework**: Django 5.2.16 (Python 3.13)
*   **Database**: PostgreSQL 16
*   **Isolation**: PostgreSQL Row-Level Security (RLS) policies enforced for `ledger_tenant_role`.
*   **Integrity Rules**: Enforced via PostgreSQL PL/pgSQL database triggers.

---

## 2. Directory Layout & Core Components

Here is where the core logic is located:

```
├── accounting/
│   ├── admin.py               # Registers all 14 models in the Django admin panel
│   ├── audit.py               # Trial Balance reports, period locking, audit checks
│   ├── bank_import.py         # CSV parser with SHA-256 deduplication and FITID checks
│   ├── middleware.py          # Tenant context manager setting app.current_tenant_id
│   ├── models.py              # Schema definition for all accounting structures
│   ├── reconciliation.py      # Bank clearing matching rules and ledger balance audits
│   ├── reversals.py           # Period-shifting journal reversal engine
│   ├── vat.py                 # Priority VAT rate lookup and control reports
│   ├── fixtures/
│   │   ├── factory.py         # Original CareCo, ConsultCo, TradeCo synthetic generator
│   │   ├── new_companies.py   # Seeder script for TechCo, LogisticsCo, CharityCo
│   │   └── generated/         # JSON fixtures with transactions and expected outcomes
│   ├── management/commands/
│   │   └── seed_db.py         # Seeder command populating all 6 tenants and reconciling them
│   └── tests/
│       ├── test_kernel.py     # Stage 1: Double-entry and RLS tests
│       ├── test_vat.py        # Stage 2: VAT lookup and control report tests
│       ├── test_bank_import.py# Stage 3: CSV import and idempotency tests
│       ├── test_evidence.py   # Stage 4: Evidence link status promotion tests
│       ├── test_reconciliation.py # Stage 5: Bank matching clearing tests
│       ├── test_audit.py      # Stage 6: VAT locking and audit check tests
│       └── test_end_to_end.py # Unified end-to-end stage verification across all 6 clients
```

---

## 3. Implemented Stages & Core Mechanics

### Stage 1: Accounting Kernel (Integrity & Isolation)
*   **Double-Entry Balancing**: Trigger `check_journal_balance` on the table `accounting_journalline`. Runs `AFTER INSERT OR UPDATE OR DELETE` to ensure total debits equal total credits for each journal.
*   **Closed Accounting Periods**: Trigger `check_period_not_closed` on `accounting_journal` and `accounting_journalline`. Blocks all mutations (inserts, updates, deletes) where the journal date falls within a closed `AccountingPeriod`.
*   **Row-Level Security (RLS)**: Policies applied to all transactional tables. In `middleware.py`, the `tenant_context` context manager runs queries inside `ledger_tenant_role` and sets the session variable `app.current_tenant_id`.

### Stage 2: VAT Rules & Control Accounts
*   **Resolution Engine**: Looks up priority rules in `VatDecisionRule` (matching supplier name and nominal account codes). Fallbacks to `VatRate` defaults.
*   **VAT Control Report**: Aggregates sales/purchase lines to verify that the balance of the VAT Control Account (`2200`) matches computed output VAT minus input VAT to the penny.

### Stage 3: Idempotent Bank CSV Imports
*   **SHA-256 Deduplication**: Hashes raw CSV contents and stores it in `ImportedFile.file_hash`. Rejects duplicate uploads.
*   **Line-Level Idempotency**: Skips statement transactions if the transaction `FITID` already exists for that tenant in the database.

### Stage 4: Purchase Ledger & Document Evidence
*   **Review Status Triggers**: Triggers `check_journal_status_default` (sets status to `RequiresReview` on new invoices/expenses) and `sync_journal_status_on_link` (promotes status to `Posted` when linked to an `EvidenceDocument`, demoting back to `RequiresReview` if the link is deleted).
*   **Period-Shifting Reversals**: Function `reverse_journal` swaps debits and credits. If the original journal's period is closed, it shifts the transaction date to today's date in the active open period.

### Stage 5: Bank Reconciliation matching
*   **Dynamic Clearing Rules**: Matches transactions to unpaid invoices. Resolves whether to clear against `2100` (Aged Creditors) or `1100` (Aged Debtors). Creates balanced payments/receipts in the bank account (`1200`).
*   **Ledger-to-Bank Audit**: Audits the bank account balance against statements, accounting for opening manual journal balances.

### Stage 6: Accountant Audit Interface
*   **Period Locking**: Finalizing a VAT return creates a `VatReturn` record. Trigger `check_vat_return_lock` blocks future entries in that date range.
*   **Trial Balance**: Read-only reporting helper returning structured debits/credits.

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
4.  **Run All Tests (41/41 passing on PostgreSQL)**:
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
