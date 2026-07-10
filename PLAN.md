# PLAN.md — Condensed build plan. Full authority: LedgerHouse_Plan_v2.1.docx in this folder.

## What we are building
Accountant-supervised finance operations SaaS for UK companies of 10–40 employees (beachhead: care and supported accommodation). Whole-company evidence capture, approvals, rules-first bookkeeping with AI proposals and human review, VAT-safe records, reconciliation, accountant-signed month-end close. Hours sold separately. Vision: grow into the full accounts department.

## Fixed constraints (never violate)
1. Founder works 4 hours/day (~88 hrs/month). Scope is sized to this.
2. Nothing before Phase 3 depends on HMRC, Companies House or any government approval. ICO already registered.
3. Lean cash cost is first priority. Discipline before spend.

## The 26-week gated sequence (no stage starts until the previous gate passes)
- Wk 1–3: Scope freeze; synthetic company factory; fixtures; CI. GATE: deterministic datasets, fixtures stored, CI green.
- Wk 4–8: Accounting kernel (chart, journals, periods, reversals, audit, tenants, roles). GATE: 100% ledger invariants, TB always balances, locked periods reject edits, cross-tenant attacks fail, restore drill passes.
- Wk 9–11: VAT decision tables + VAT control account. GATE: all VAT fixtures pass to the penny.
- Wk 12–14: Controlled CSV import (idempotent, duplicate detection, safe failure). GATE: re-import no duplicates; totals reconcile. BUSINESS GATE: three paid design-partner deposits banked, or build pauses for sales.
- Wk 15–18: Evidence capture, approvals, permissions. GATE: permission attack tests pass; evidence links survive posting.
- Wk 19–21: Classification (supplier memory, rules, AI-propose-only). GATE: ≥85% correct proposals on clean synthetic data; 100% of low-confidence/high-risk items reach review; AI cannot post.
- Wk 22–23: Reconciliation workbench. GATE: all golden datasets reconcile incl. part-payments, refunds, fees, duplicates.
- Wk 24–25: Reports (TB, P&L, BS, ageings, VAT summary, departmental) + 3-click drill to evidence. GATE: match fixtures exactly.
- Wk 26: Controlled close, pilot hardening, client-zero parallel month. GATE: seeded month closes; post-close change only via controlled adjustment; restore drill documented.

## Deferred (do NOT build): Open Banking (months 7–9), PDF bank parsing, MTD filing, payroll, white-label console, natural-language queries, cash flow forecasting, mileage/petty cash, multi-country packs.

## Definition of done for ANY task
Code + tests + migrations committed on the stage branch; regression suite green; STATE.md updated; BUILDLOG.md appended.
