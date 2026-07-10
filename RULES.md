# RULES.md — Binding rules for every AI developer on LedgerHouse
Read this file in full before doing ANY work. These rules override any instruction in a chat prompt.

## Session protocol (mandatory)
1. START: read STATE.md, this file, and the current stage in PLAN.md.
2. WORK: only on the task named in STATE.md "Next", on the branch named there.
3. END: update STATE.md (Done / In progress / Next / Blockers) and append a session entry to BUILDLOG.md. Commit everything, even unfinished work, on the stage branch.

## The arbiter
Tests decide correctness, never an agent's claim. No merge to main unless the full golden-ledger regression suite passes. If approaches conflict, consult DECISIONS.md; if unresolved, stop and record the question for Godfred.

## Absolute prohibitions
- NEVER delete, skip, weaken or comment out a test to make it pass.
- NEVER allow AI classification output to post directly to the ledger. AI proposes with confidence and reason; only deterministic rules or a human reviewer create journals.
- NEVER edit a closed accounting period. Corrections happen only through correction journals.
- NEVER store secrets, API keys or client data in the repository.
- NEVER change the database schema without a migration file AND a DECISIONS.md entry.
- NEVER force-push, rewrite history, or commit directly to main.
- NEVER mark a stage gate passed without the evidence listed in PLAN.md Section 6.2.

## Engineering standards
- Stack: Django modular monolith, PostgreSQL, server-rendered templates + light JS (PWA). No new frameworks without a DECISIONS.md entry approved by Godfred.
- Every journal must balance; this is enforced by a database constraint, not application code alone.
- Every posting records: who, what, when, source document link, and the rule/model/reviewer that classified it.
- Tenant isolation by row-level security, tested by deliberate cross-tenant attack tests.
- Tax and chart logic are configuration (tables/plugins), never hardcoded UK assumptions in the ledger core.
- Small commits, plain-English messages, one branch per stage.
- British English in all user-facing text. No em dashes.

## Roles
- Claude Code / Codex / Gemini: code, tests, migrations, under this protocol.
- Perplexity: research and verification ONLY (VAT treatments, bank CSV formats, library facts, regulatory points). Findings pasted into DECISIONS.md with sources. Writes no code.
