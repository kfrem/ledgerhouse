# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 2 — VAT decision tables and VAT control account (PLAN.md Section 6.2, weeks 9–11) - COMPLETE.
Next Stage: Stage 3 — Controlled CSV bank import (PLAN.md Section 6.2, weeks 12–14)
Branch: stage-2-vat

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`, `VatRate`, `VatDecisionRule`.
- Implemented RLS and custom constraint triggers for balancing, locked periods, and audit immutability (Stage 1).
- Implemented VAT decision tables lookup prioritizing patterns and account prefixes (Stage 2).
- Implemented VAT reporting utility reconciling Output, Input, and Net VAT against the VAT control account (2200).
- Created unit tests verifying VAT rate resolution, RLS isolation on rules, and penny-perfect report reconciliation across all 3 seeded companies.
- Verified 100% green test suite (21 passed) inside PostgreSQL Docker environment.

## In progress
- (none - ready for Stage 3)

## Next (in order)
1. progression to Stage 3: Controlled CSV bank import (idempotency, duplicate detection by hash, date, amount, reference, safe failure handling).

## Stage 2 exit gate (do not proceed to Stage 3 until ALL true)
- [x] All VAT fixtures pass to the penny (output, input, and net VAT reconciled)
- [x] Configurable VAT rate and decision tables (database rules/rates isolation enforced by RLS)

## Blockers
- (none)

## Notes for the next agent
- Stage 2 migrations have been successfully generated and executed in Docker.
- PYTEST runs with migrations by default now. Ensure docker environment is used to run PostgreSQL-specific test validations.
