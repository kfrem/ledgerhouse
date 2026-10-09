# LedgerHouse Legal Review Brief

Date: 13 August 2026

LedgerHouse is an accounting-workflow application operated by KAFS Limited,
trading as KAFS Automation. It stores client accounting records, uploaded
evidence, audit events and optional integration settings. The application has
public privacy and terms pages, but those documents remain drafts until a
qualified UK legal adviser has reviewed and approved them for the intended
commercial model.

## Review Requested

Please review the following before paid public launch:

1. Customer terms: service scope, liability limits, suspension, support,
   payment/renewal terms and the distinction between software and regulated
   accounting/tax advice.
2. Privacy notice and data-processing terms: controller/processor roles,
   lawful basis, special-category data handling if it arises, international
   transfers, sub-processors, retention periods and data-subject rights.
3. Data retention and deletion: a defensible retention schedule for accounting
   evidence, tax records, audit events, backups and former-client data.
4. Security and incident response: notification responsibilities, customer
   contact route, breach escalation and the supplier/sub-processor register.
5. Marketing and onboarding: consent wording, trial/billing notices and client
   authority wording before HMRC, Companies House or banking features are used.

## Technical Evidence Available

- Public pages: `/privacy/` and `/terms/`.
- Role-separated client and practice workspaces with audit events.
- Encrypted-field configuration and PostgreSQL tenant controls.
- Nightly database backups plus an isolated restore rehearsal.
- Provider integrations designed to fail closed until configured.

## Explicit Limits

This brief is not legal advice and is not itself legal sign-off. LedgerHouse
must not present these documents as approved until written approval is retained
by KAFS Limited.
