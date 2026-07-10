# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 5 — Bank reconciliation engine (PLAN.md Section 6.2, weeks 19–22) - COMPLETE.
Next Stage: Stage 6 — Accountant audit interface (PLAN.md Section 6.2, weeks 23–26)
Branch: stage-5-reconciliation

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`, `VatRate`, `VatDecisionRule`, `ImportedFile`, `BankTransaction`, `EvidenceDocument`, `JournalEvidenceLink`, `BankReconciliation`.
- Implemented RLS and custom triggers for double-entry balancing, closed periods, and audit immutability (Stage 1).
- Implemented priority VAT rules lookup and VAT control account report calculations (Stage 2).
- Implemented bank CSV parser with file hashing, validation, and transaction-level idempotency skipping (Stage 3).
- Implemented status review triggers for link additions/deletions, real-time review metrics, and closed period date shifting reversals (Stage 4).
- Implemented bank matching engine generating clearing journals against trade debt/credit accounts and ledger-to-bank balance audits (Stage 5).
- Created unit tests verifying default review status, trigger-based status updates/reversions on linking/unlinking, reversal swap calculations, closed period date shifting, bank CSV file parsing, RLS isolation on bank/evidence/reconciliation tables, clearing journal creation, and 100% synthetic statement reconciliation.
- Verified 100% green test suite (36 passed) inside PostgreSQL Docker environment.

## In progress
- (none - ready for Stage 6)

## Next (in order)
1. progression to Stage 6: Accountant audit interface (read-only trial balance export, VAT return locking, and immutable audit logs).

## Stage 5 exit gate (do not proceed to Stage 6 until ALL true)
- [x] reconciles 100% of synthetic bank statement to ledger (proven in CareCo fixture test)
- [x] ledger-to-bank balance verification helper is implemented and green

## Blockers
- (none)

## Notes for the next agent
- Database migrations are fully applied and up to date.
- Safe `current_setting('app.current_tenant_id', true)` helper is implemented in middleware to avoid transaction aborts.
