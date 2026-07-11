# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Roadmap Completion — Phase 1, Phase 2, and Phase 3 - COMPLETE.
All Stages & Phases — COMPLETE.
Branch: stage-6-audit

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`, `VatRate`, `VatDecisionRule`, `ImportedFile`, `BankTransaction`, `EvidenceDocument`, `JournalEvidenceLink`, `BankReconciliation`, `VatReturn`, `BankFeedConnection`.
- Implemented RLS and custom triggers for double-entry balancing, closed periods, and audit immutability (Stage 1).
- Implemented priority VAT rules lookup and VAT control account report calculations (Stage 2).
- Implemented bank CSV parser with file hashing, validation, and transaction-level idempotency skipping (Stage 3).
- Implemented status review triggers for link additions/deletions, real-time review metrics, and closed period date shifting reversals (Stage 4).
- Implemented bank matching engine generating clearing journals against trade debt/credit accounts and ledger-to-bank balance audits (Stage 5).
- Implemented trial balance reports, VAT period locking triggers, and accountant system-wide audit checks (Stage 6).
- Generated three new synthetic client companies (TechCo SaaS, LogisticsCo Haulage, CharityCo Foundation) to test diverse tax codes, outside scope grants, reduced rate fuel costs, and multi-department fund tracking.
- Created custom `seed_db` command loading all 6 companies and running the reconciliation matches.
- Built a comprehensive end-to-end test suite (`test_end_to_end.py`) executing all 6 stages of kernel logic sequentially for all 6 clients.
- Built Open Banking Sync Engine (`open_banking.py`) for automatic feed transaction ingestion, virtual ImportedFile tracking, and auto-matching (Phase 2).
- Built HMRC Making Tax Digital (MTD) VAT Filing Engine (`mtd.py`) serializing 9-box VAT returns and submitting to mock HMRC API (Phase 3).
- Built Payroll Journal Importer (`payroll_cis.py`) parsing payroll CSV files to post balanced multi-department staff salary manual journals (Phase 3).
- Built CIS Subcontractor Withholding helper (`payroll_cis.py`) splitting supplier invoices into tax liabilities and net payables (Phase 3).
- Built White-Label Accountant Console (`console.py`) consolidating multi-tenant close, audit, and connection health metrics (Phase 3).
- Verified 100% green test suite (47 passed) inside PostgreSQL Docker environment.

## In progress
- (none - all phases completed)

## Next (in order)
- accountant-supervised production staging runs.

## Stage 6 exit gate
- [x] accountant runs audit check (proven in test suite)
- [x] exports full client trial balance (proven in test suite)
- [x] end-to-end verification of 6 diverse companies complete
- [x] Open Banking feeds, MTD filing, Payroll, CIS, and White-label Console complete (Phase 2 & 3)

## Blockers
- (none)

## Notes for the next agent
- The platform is fully constructed, tested, and ready for deployment.
- Strict Row-Level Security, immutable audit logging, balanced journal constraints, and date-locked period edits are fully enforced at the PostgreSQL database engine layer.
- Seeding and testing verify CareCo, ConsultCo, TradeCo, TechCo, LogisticsCo, and CharityCo.
