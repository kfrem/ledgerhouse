# HMRC Customer Authorisation Self-Certification Evidence

Date: 2026-07-13

Software: LedgerHouse / KAFS UK Accounting SaaS.

## HMRC Authorisation Details

These values support the HMRC Developer Hub customer-authorisation checklist.

- Software name: `LedgerHouse`
- Customer-data server location: `Germany (EU), Hetzner Falkenstein data centre for the planned production deployment`
- Privacy policy URL: `https://ledgerhouse.finaccord.pro/privacy/`
- Terms and conditions URL: `https://ledgerhouse.finaccord.pro/terms/`

## HMRC Submission Status

On 2026-07-13, the HMRC Developer Hub production credentials checklist showed all terms-of-use sections as completed:

- Organisation details
- Marketing your software
- Development practices
- Service management practices
- Handling personal data
- Software security
- Fraud prevention data
- Customers authorising your software

The production credentials request was then confirmed and sent through the HMRC Developer Hub. The confirmation page stated: `We have received your request for production credentials`.

## Product Evidence

- Public privacy route: `/privacy/`
- Public terms route: `/terms/`
- HMRC authorisation uses OAuth and does not store HMRC sign-in passwords.
- Stored HMRC access and refresh tokens are encrypted at application field level.
- Customer data export is available for provider switching.

## Test Evidence

- `accounting.tests.test_client_portal_workflows accounting.tests.test_hmrc_sandbox`: 43 tests OK on 2026-07-13.
- Full suite after public policy pages and HMRC validator support: 103 tests OK on 2026-07-13.
- Full suite after HMRC production credentials request submission: 103 tests OK on 2026-07-13.
- Django system check after HMRC production credentials request submission: no issues.

## Production Follow-Up

Before broad paid public launch, the privacy notice and terms should be reviewed as customer-facing legal documents. The routes and content are sufficient for the current controlled HMRC production credentials request.
