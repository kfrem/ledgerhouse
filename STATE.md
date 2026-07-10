# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 4 — Purchase ledger and evidence capture (PLAN.md Section 6.2, weeks 15–18) - COMPLETE.
Next Stage: Stage 5 — Bank reconciliation engine (PLAN.md Section 6.2, weeks 19–22)
Branch: stage-4-evidence

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`, `VatRate`, `VatDecisionRule`, `ImportedFile`, `BankTransaction`, `EvidenceDocument`, `JournalEvidenceLink`.
- Implemented RLS and custom triggers for double-entry balancing, closed periods, and audit immutability (Stage 1).
- Implemented priority VAT rules lookup and VAT control account report calculations (Stage 2).
- Implemented bank CSV parser with file hashing, validation, and transaction-level idempotency skipping (Stage 3).
- Implemented status review triggers for link additions/deletions, real-time review metrics, and closed period date shifting reversals (Stage 4).
- Created unit tests verifying default review status, trigger-based status updates/reversions on linking/unlinking, reversal swap calculations, closed period date shifting, and cross-tenant isolation.
- Verified 100% green test suite (32 passed) inside PostgreSQL Docker environment.

## In progress
- (none - ready for Stage 5)

## Next (in order)
1. progression to Stage 5: Bank reconciliation engine (matching bank lines to ledger lines, net-zero clearing, and ledger balance checks).

## Stage 4 exit gate (do not proceed to Stage 5 until ALL true)
- [x] Every debit/credit is matching/evidenced or marked 'RequiresReview' (trigger enforced)
- [x] Total review count is tracked (get_review_metrics helper verified)

## Blockers
- (none)

## Notes for the next agent
- Stage 4 migrations have been successfully generated and executed in Docker.
- PYTEST runs with migrations by default now. Ensure docker environment is used to run PostgreSQL-specific test validations.
