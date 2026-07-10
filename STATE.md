# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 3 — Controlled CSV bank import (PLAN.md Section 6.2, weeks 12–14) - COMPLETE.
Next Stage: Stage 4 — Purchase ledger and evidence capture (PLAN.md Section 6.2, weeks 15–18)
Branch: stage-3-import

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`, `VatRate`, `VatDecisionRule`, `ImportedFile`, `BankTransaction`.
- Implemented RLS and custom constraint triggers for balancing, locked periods, and audit immutability (Stage 1).
- Implemented VAT decision tables lookup prioritizing patterns and account prefixes (Stage 2).
- Implemented VAT reporting utility reconciling Output, Input, and Net VAT against the VAT control account (Stage 2).
- Implemented bank CSV parsing with header validation, SHA-256 file hashing, fitid deduplication, and line-level idempotency skipping (Stage 3).
- Created unit tests verifying CSV parsing success, file-level deduplication, transaction-level idempotency, validation failures rollback, and RLS isolation on bank records.
- Verified 100% green test suite (27 passed) inside PostgreSQL Docker environment.

## In progress
- (none - ready for Stage 4)

## Next (in order)
1. progression to Stage 4: Purchase ledger and evidence capture (evidence matching, invoice/expense/receipt uploads, review flags, and structured transaction correction journals).

## Stage 3 exit gate (do not proceed to Stage 4 until ALL true)
- [x] Re-import of same file causes no duplicates (file-level hashing and fitid deduplication)
- [x] Totals reconcile exactly (import counts and transactions verified)

## Blockers
- (none)

## Notes for the next agent
- Stage 3 migrations have been successfully generated and executed in Docker.
- PYTEST runs with migrations by default now. Ensure docker environment is used to run PostgreSQL-specific test validations.
