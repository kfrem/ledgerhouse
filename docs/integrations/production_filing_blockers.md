# Production Filing Blockers

## Purpose

This separates local product readiness from external filing readiness. LedgerHouse can continue to build and test client uploads, bookkeeping review, VAT preparation, reporting, Docker, PostgreSQL and sandbox workflows locally. Real government filing is blocked until external approvals and credentials are confirmed.

## HMRC

Local and sandbox work can continue with the current HMRC developer setup.

Production filing still requires:

- HMRC production application credentials for each API being used.
- Confirmed API subscriptions for the relevant taxes and filing obligations.
- Agent/client authorisation flow working with the correct Government Gateway or agent services account.
- Production redirect URI configured to the live domain.
- Fraud-prevention headers validated against HMRC production requirements.
- Filing test evidence retained for VAT and any later taxes added.

## Companies House

Read-only Companies House API access may be available through a developer key.

Actual filing or submission capability may require:

- The correct Companies House filing product/API access.
- Presenter or authorised filing credentials where required.
- Company authentication code handling rules.
- Confirmation of which forms/accounts/confirmation-statement filings are supported by the selected API.
- A secure production secrets process before any filing credential is stored or used.

## Local Work Not Blocked

- Client portal design and logic.
- Practice client management.
- Evidence upload and review.
- Bank import and review.
- Ledger review and approval.
- VAT workspace preparation and sandbox calls.
- Management reports and exports.
- Docker and PostgreSQL local verification.
- Automated test coverage.

## External Work Still Blocked

- Real HMRC submissions.
- Real Companies House filings.
- Live bank-feed provider connections.
- Production payment-card or billing changes.
- Production deployment while the user wants to avoid server cost.
