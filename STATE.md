# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 6 — Accountant audit interface & End-to-End Verification - COMPLETE.
All Stages (0 to 6) — COMPLETE.
Branch: stage-6-audit

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`, `VatRate`, `VatDecisionRule`, `ImportedFile`, `BankTransaction`, `EvidenceDocument`, `JournalEvidenceLink`, `BankReconciliation`, `VatReturn`.
- Implemented RLS and custom triggers for double-entry balancing, closed periods, and audit immutability (Stage 1).
- Implemented priority VAT rules lookup and VAT control account report calculations (Stage 2).
- Implemented bank CSV parser with file hashing, validation, and transaction-level idempotency skipping (Stage 3).
- Implemented status review triggers for link additions/deletions, real-time review metrics, and closed period date shifting reversals (Stage 4).
- Implemented bank matching engine generating clearing journals against trade debt/credit accounts and ledger-to-bank balance audits (Stage 5).
- Implemented trial balance reports, VAT period locking triggers, and accountant system-wide audit checks (Stage 6).
- Generated three new synthetic client companies (TechCo SaaS, LogisticsCo Haulage, CharityCo Foundation) to test diverse tax codes, outside scope grants, reduced rate fuel costs, and multi-department fund tracking.
- Created custom `seed_db` command loading all 6 companies and running the reconciliation matches.
- Built a comprehensive end-to-end test suite (`test_end_to_end.py`) executing all 6 stages of kernel logic sequentially for all 6 clients.
- Verified 100% green test suite (41 passed) inside PostgreSQL Docker environment.

## In progress
- (none - all stages completed)

## Next (in order)
- accountant-supervised production staging runs.

## Stage 6 exit gate
- [x] accountant runs audit check (proven in test suite)
- [x] exports full client trial balance (proven in test suite)
- [x] end-to-end verification of 6 diverse companies complete

## Blockers
- (none)

## Notes for the next agent
- The platform is fully constructed, tested, and ready for deployment.
- Strict Row-Level Security, immutable audit logging, balanced journal constraints, and date-locked period edits are fully enforced at the PostgreSQL database engine layer.
- Seeding and testing verify CareCo, ConsultCo, TradeCo, TechCo, LogisticsCo, and CharityCo.
