# STATE.md — Single source of current truth. Update at the END of every session.

## Current stage
Stage 0 — Scope freeze and synthetic company factory (PLAN.md Section 6.2, weeks 1–3)
Branch: stage-0-foundation

## Done
- Initialized Git repository, Docker Compose (Django + PostgreSQL), CI running pytest on push/PR.
- Documented exclusions list in EXCLUSIONS.md and DECISIONS.md.
- Built synthetic company factory producing CareCo, ConsultCo, and TradeCo variants deterministically from a fixed seed.
- Generated and saved expected outcomes as controlled JSON fixtures.
- Created unit tests verifying double-entry balancing, trial balance zero-sums, VAT reconciliations, aging ledgers, and rejection flows.

## In progress
- (none)

## Next (in order)
- progression to Stage 1: Accounting Kernel (Chart, Journals, Periods, Reversals, Tenant Isolation, RLS, Audit, Roles)

## Stage 0 exit gate (do not proceed to Stage 1 until ALL true)
- [x] Datasets deterministic from seed
- [x] Expected results stored as fixtures
- [x] CI green on the fixture suite
- [x] Exclusions list signed off in DECISIONS.md

## Blockers
- (none)

## Notes for the next agent
- The synthetic company factory is implemented in `accounting/fixtures/factory.py` with seed=42.
- Fixtures are generated and stored in `accounting/fixtures/generated/` as JSON files.
- Testing is run via pytest (`.venv\Scripts\pytest` or just `pytest` in Docker/CI). All tests pass.

