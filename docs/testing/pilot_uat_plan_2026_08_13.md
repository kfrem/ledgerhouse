# LedgerHouse Controlled Pilot UAT Plan

Date: 13 August 2026

## Scope

Use synthetic data first, then a small, explicitly approved pilot group. Do
not run HMRC returns, Companies House filings, payment collection, bank-feed
syncs or live notifications as part of this plan unless their separate provider
authorisation has been completed.

## Roles

- Client user: upload evidence, answer queries, approve packs and view reports.
- Practice reviewer: categorise evidence, review journals, reconcile bank CSV
  imports, post payroll, complete month-end and release approved packs.
- Practice manager: inspect the exception register, workload, audit timeline
  and production register.

## Acceptance Journeys

1. Invite and sign in a client user; confirm the user cannot access another
   client workspace.
2. Upload valid PDF/image/CSV/XLSX evidence and confirm unsafe or malformed
   files are rejected with a clear outcome.
3. Review an evidence item, create or review its journal and confirm the audit
   trail records the action.
4. Import a bank CSV, reconcile a line, and confirm unmatched lines remain in
   the exception register.
5. Import a valid payroll CSV and confirm the balanced payroll journal and
   payroll period register are created once only.
6. Post accrual, prepayment and depreciation schedules; repeat the action and
   confirm no duplicate journals are created.
7. Attempt month-end close with a missing control and confirm it is rejected;
   then complete all gates and confirm the period locks.
8. Generate a management pack, obtain client approval in the controlled test
   flow, release it once and verify its release audit record.
9. Review annual-accounts filing readiness without sending a filing.

## Exit Criteria

Each journey passes for a client user and practice user on desktop and mobile
layouts. Any defect is recorded with its route, account role, expected result,
actual result, screenshot where useful and retest result. Provider actions stay
disabled unless separately approved.
