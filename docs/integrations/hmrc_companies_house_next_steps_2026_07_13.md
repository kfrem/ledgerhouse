# HMRC And Companies House Next Steps

Date: 2026-07-13

This document records what is complete and what still depends on HMRC, Companies House, live credentials or public deployment.

## HMRC Status

Completed:

- HMRC Developer Hub production credentials checklist completed.
- Production credentials request submitted for LedgerHouse / KAFS UK Accounting SaaS.
- HMRC confirmation page stated: `We have received your request for production credentials`.
- VAT MTD workflow is implemented locally.
- HMRC OAuth scaffolding is implemented.
- HMRC token storage is encrypted.
- Fraud-prevention headers for `WEB_APP_VIA_SERVER` are implemented.
- HMRC sandbox fraud-prevention validator returned `VALID_HEADERS`.
- Local automated tests cover HMRC authorisation URL generation, callback token storage, VAT obligations, VAT payloads, VAT review gating and VAT submission handling.

Blocked externally:

- HMRC must review and approve production credentials.
- Live production HMRC client ID/secret must be saved outside Git after approval.
- Production redirect URI must be set to the final live HTTPS domain when deployment resumes.
- Live OAuth and live filing must be tested only with a controlled account and deliberate approval.

Operational rule:

- Keep live filing disabled until HMRC production credentials are approved, production environment variables are set, and a controlled filing test is agreed.

## Companies House Status

Completed:

- Existing Companies House Developer Hub account and app were identified.
- Read-only Companies House API key support exists through environment variable or local key file.
- Local read-only Companies House integration can retrieve company profiles.
- Practice users can create/match a LedgerHouse client from an official Companies House profile.
- Audit event is recorded when a Companies House profile is used to create or match a client.
- Automated tests cover key configuration, profile retrieval, API error handling and client creation.

Blocked externally:

- Software filing is not enabled by the read-only REST API key alone.
- Presenter ID/code must be received and stored outside Git before any filing workflow can be considered.
- Fee filings may require a Companies House credit account.
- Company authentication code handling rules must be confirmed before storing or using any filing authorisation data.

Operational rule:

- Treat Companies House as read-only until presenter/filing credentials and the exact supported filing API are confirmed.

## Local Development That Can Continue

- Client upload and review workflow.
- Practice work queues.
- Management reporting.
- Client data export.
- VAT review workflow before live filing.
- Companies House profile lookup and client setup.
- Production readiness checks.
- Legal/customer documents.
- Deployment scripts and smoke tests.

## External Items To Resolve Later

- HMRC approval email/result.
- HMRC live credentials.
- Final public hosting decision.
- Live HTTPS DNS test.
- Companies House presenter details.
- Companies House credit account if paid filings are needed.
- Legal review of terms, privacy notice and data processing agreement.
