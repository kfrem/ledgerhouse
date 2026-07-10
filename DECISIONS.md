# DECISIONS.md — Append-only architectural decision log. Never edit past entries.

## D-001 | 2026-07-10 | Stack
Django modular monolith + PostgreSQL + server-rendered templates (PWA). Reason: test tooling, ORM integrity, admin, founder familiarity. Decided in Plan v2.1 Section 7.1. Approved: Godfred.

## D-002 | 2026-07-10 | AI posting rule
AI classification proposes only, with confidence and stored reason. Only deterministic rules or human review create journals. Approved: Godfred (panel consensus).

## D-003 | 2026-07-10 | Internationalisation boundary
jurisdiction, currency, tax_registration, accounting_basis are first-class fields; tax codes are configuration tables; UK is the first plugin pack. Approved: Godfred.

## D-004 | 2026-07-10 | Pilot client eligibility criteria
The first three pilot clients must meet the following strict criteria:
- UK limited company.
- One legal entity.
- GBP functional currency only.
- One or two bank accounts.
- Standard/simple VAT or non-VAT profile.
- Maximum 500 transactions per month.
- Maximum three departments.
- Maximum two approval workflows.
- No inventory.
- No CIS (Construction Industry Scheme).
- No import VAT.
- No multi-currency.
- No client-money handling.
- No payment execution.
- No payroll processing in LedgerHouse.
- No charities, CICs, groups, grant-consolidation entities, or complex funding structures.
Reason: To limit operational complexity during Stage 0 and Stage 1 pilot phase. Approved: Godfred.

## D-005 | 2026-07-10 | Real Data Admission Gate
No real client data may be uploaded, processed, or sent to any external service until Godfred explicitly confirms that the following are complete:
- Suitable client contract and pilot agreement.
- Data Protection Impact Assessment (DPIA).
- Data flow map.
- Data Processing Agreement (DPA) and privacy notice.
- Approved sub-processor list.
- AML and professional-scope confirmation.
- Professional indemnity (PI) insurance confirmation.
- Security/access-control checklist.
- Encrypted backup and restore evidence.
- Named client data controller/contact.
- Written client permission for controlled parallel-run processing.
Reason: To enforce strict data privacy and regulatory compliance, and prevent exposure of production/client data. Approved: Godfred.

## D-006 | 2026-07-10 | Month-close service boundary
The "working day 7" month-end close target applies only where complete bank data, source evidence, approval decisions, and client responses are provided according to the agreed timetable. Missing or disputed information pauses the timetable. Reports are accountant-reviewed only where a named authorised accountant has completed sign-off. No assurance opinion is implied.
Reason: To clarify service liability and prevent unrealistic expectations on close timing when client dependencies are late. Approved: Godfred.

(append new entries below in the same format: D-00N | date | title | decision | reason | approved by)
