# LedgerHouse Customer Document Pack

Date: 2026-07-13

Purpose: working drafts and checklists for the legal/customer documents needed before external paid clients are onboarded.

These documents are operational drafts, not legal advice. They should be reviewed before public launch.

## Documents Needed

- Privacy notice.
- SaaS terms and conditions.
- Data processing agreement.
- Security contact and vulnerability reporting statement.
- Retention and deletion policy.
- Client onboarding consent wording.
- HMRC authorisation explanation.

## Privacy Notice Draft Points

LedgerHouse should explain:

- What data is processed: company records, users, uploaded evidence, bank transactions, bookkeeping entries, VAT records, reports, support requests and audit logs.
- Why data is processed: bookkeeping, accounts production, VAT review, management reporting, compliance support and client advice.
- Lawful basis: contract, legal obligation and legitimate interests depending on the service.
- Who receives data: the client, authorised practice users, HMRC where authorised, Companies House where applicable, hosting/storage providers and professional advisers where needed.
- HMRC access: customers authorise HMRC access through OAuth; LedgerHouse does not store HMRC passwords.
- Retention: records are retained for the contract period and statutory/accounting retention periods unless lawfully deleted earlier.
- Customer rights: access, correction, export, objection and deletion where applicable.
- Security: access controls, tenant separation, encrypted third-party tokens, HTTPS in production and audit records.
- Contact route: monitored business support/security contact.

## SaaS Terms Draft Points

LedgerHouse terms should cover:

- Who may use the service.
- Client responsibility for supplying accurate source documents.
- Accountant/practice role in reviewing and preparing records.
- HMRC and Companies House authorisation requirements.
- No filing without appropriate authorisation and review.
- Service availability and maintenance.
- Support and incident reporting.
- Fees, if any, and payment terms.
- Data export on termination.
- Limitations of liability.
- Suspension for misuse or non-payment.
- Governing law and dispute handling.

## Data Processing Agreement Draft Points

The DPA should cover:

- Controller/processor roles for KAFS/LedgerHouse and client.
- Processing purpose and categories.
- Sub-processors such as hosting, storage, email and monitoring providers.
- Security measures.
- Breach notification process.
- Data subject request assistance.
- Return/deletion of data.
- International transfers, if any.
- Audit and evidence rights.

## Security Contact Statement Draft

Recommended public wording:

```text
If you need to report a security risk affecting LedgerHouse, contact info@kafs-ltd.com with the subject "LedgerHouse security report". Include the affected page, account, time observed and steps to reproduce where safe. Do not include unnecessary personal data. We will acknowledge and triage security reports as soon as practicable.
```

Production improvement:

- Add a dedicated `security@finaccord.pro` or equivalent monitored address.

## Retention And Deletion Draft

Suggested policy structure:

- Source documents and accounting records: retained for the statutory accounting/tax period unless a longer contract or legal obligation applies.
- Audit logs: retained for security, compliance and dispute evidence.
- HMRC tokens: deleted or revoked when the client disconnects HMRC authorisation or terminates service.
- Bank consent tokens: deleted or revoked when bank-feed access is disconnected.
- Support requests: retained while relevant to service delivery and dispute evidence.
- Data export: provided to the client before deletion where contractually required.

## Client Onboarding Consent

Before a client uses live HMRC features, the onboarding wording should explain:

- The client is authorising LedgerHouse to access relevant HMRC data for the selected tax service.
- The client can revoke authorisation through HMRC or LedgerHouse support.
- LedgerHouse stores authorisation tokens, not HMRC passwords.
- Filing will only happen after review/approval gates are completed.

## Legal Review Checklist

- Confirm company/provider identity.
- Confirm controller/processor roles.
- Confirm insurance/liability position.
- Confirm retention periods.
- Confirm sub-processors.
- Confirm customer cancellation/export process.
- Confirm HMRC and Companies House authorisation wording.
- Confirm security contact route.
