# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 1 — Accounting Kernel (PLAN.md Section 6.2, weeks 4–8) - COMPLETE.
Next Stage: Stage 2 — VAT decision tables and VAT control account (PLAN.md Section 6.2, weeks 9–11)
Branch: stage-1-kernel

## Done
- Set up Docker Compose, Python virtual environment, CI configuration (Stage 0).
- Created database models: `Tenant`, `NominalAccount`, `AccountingPeriod`, `Journal`, `JournalLine`, `AuditEvent`.
- Implemented PostgreSQL restricted role `ledger_tenant_role` and enabled/forced Row-Level Security (`FORCE ROW LEVEL SECURITY`) on all multi-tenant tables.
- Implemented deferred PostgreSQL triggers to enforce journal balancing (Total Debits = Total Credits) upon transaction commit.
- Implemented BEFORE triggers to enforce period locking (blocks inserts/updates/deletes on journals inside closed periods).
- Implemented triggers to block update/delete on `AuditEvent` to make audit logs immutable.
- Built a multi-tenant middleware and connection context managers to set/reset `app.current_tenant_id` and the restricted role session state.
- Created `test_kernel.py` test suite proving ledger invariants, period locking, audit immutability, and tenant RLS isolation.
- Loaded CareCo synthetic fixtures, posted to the ledger kernel database, and reconciled expected results to the penny.

## In progress
- (none - awaiting gate review and progression approval)

## Next (in order)
1. progression to Stage 2: VAT decision tables and VAT control account.

## Stage 1 exit gate (do not proceed to Stage 2 until ALL true)
- [x] 100% ledger invariants (Total Debits = Total Credits database enforced)
- [x] Trial balance always balances (zero-sum verified in test suite)
- [x] Locked periods reject edits (database trigger enforced)
- [x] Cross-tenant access attempts fail (PostgreSQL RLS enforced and tested)

## Blockers
- (none)

## Notes for the next agent
- Pytest is configured to run migrations by default (removed `--nomigrations` from `pytest.ini`). This is necessary to test RLS policies and database constraints.
- Tests can be run locally using `pytest` or inside the container using `docker compose run --rm web pytest`. Both environments are 100% green.
