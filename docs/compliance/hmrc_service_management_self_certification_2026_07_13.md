# HMRC Service Management Self-Certification Evidence

Date: 2026-07-13

Software: LedgerHouse / KAFS UK Accounting SaaS.

## Scope

This record supports the HMRC Developer Hub service-management checklist answers for the production credentials request.

## Security Risk Or Incident Contact Method

HMRC asks whether customers or third parties have a way to tell the software provider about a security risk or incident.

The current product and operating setup support answering **Yes**:

- Authenticated client users can submit support/advice requests from the client portal through the `Ask your accountant` form.
- Requests are persisted as `ClientRequest` records and surfaced in the practice dashboard workbench.
- The practice dashboard includes a live client questions queue for triage.
- The developer account uses the business contact email `info@kafs-ltd.com`, which is available for external HMRC/developer correspondence and can be used for third-party security contact while the public support policy is formalised.

## Evidence In Code And Tests

- Client request model and workflow: `accounting/models.py`, `accounting/views.py`.
- Client portal support form: `templates/accounting/client_portal.html`.
- Practice workbench request queue: `templates/accounting/dashboard.html`.
- Workflow tests: `accounting/tests/test_client_portal_workflows.py`.
- Latest focused test result: `36 passed` for client portal and HMRC workflow tests.
- Latest full test result: `103 passed`.

## Security Breach Notification Process

HMRC asks whether there is a process for notifying HMRC in the case of a security breach.

The controlled operating process is:

1. Triage the reported risk or incident through the practice/support queue or business contact mailbox.
2. Identify whether HMRC customer data, OAuth credentials, HMRC API credentials, VAT data or personal data may be affected.
3. If HMRC-related data or credentials may be affected, log a ticket with HMRC Developer Hub Support within 72 hours.
4. Provide HMRC with the breach contact name, telephone/contact details, affected application, affected API scopes and immediate containment actions.
5. Where personal data may be affected, assess ICO reporting duties and notify the ICO within 72 hours where required.
6. Rotate affected credentials, revoke affected customer authorisations where appropriate, preserve audit evidence and document remediation.

Responsible individual for the current HMRC Developer Hub application: Godfred Frimpong.

## Production Follow-Up

Before broad public launch, the public website should include a dedicated security contact statement, for example `security@finaccord.pro` or an equivalent monitored address, and an incident response process should be published internally.

For HMRC production-credentials self-certification, the current controlled product has a defensible contact route and internal triage workflow.
