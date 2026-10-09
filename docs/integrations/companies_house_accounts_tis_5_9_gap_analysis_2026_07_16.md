# Companies House Accounts TIS 5.9 Gap Analysis

Date reviewed: 2026-07-16  
Document reviewed: `Companies_House_technical_interface_specification__TIS__for_accounts_5.9__003_.pdf`  
Document issue date: 2026-04-01  
Document status: Final  
Scope reviewed against LedgerHouse local codebase.

## Conclusion

LedgerHouse currently follows the Companies House requirements only where the product uses the public company-data REST API for read-only lookup. The attached TIS is for electronic accounts filing through the Companies House XML Gateway using iXBRL or package ZIP submissions. That filing capability is not currently implemented and must remain disabled until the missing filing components are built, tested and authorised.

The current app correctly treats Companies House filing as an external/blocked launch gate. I also updated the app so the Companies House workspace explicitly states that accounts filing is not enabled by the public REST API key.

## What The TIS Requires For Accounts Filing

The TIS supplement says accounts filing must be developed with the full Companies House filing TIS 5.0 or later, including:

- overall electronic filing interface structure
- message envelope and document content
- authentication mechanism
- testing arrangements

For non-package accounts submissions:

- accounts must be submitted as iXBRL
- PDF, TIF, Word, spreadsheet and similar formats are not allowed as electronic accounts submissions
- the iXBRL must be Base64 encoded inside the `<Document><Data>` element of the `<FormSubmission>` body of the GovTalk envelope
- the same key company data, such as company number, must be present in both the form submission XML and the iXBRL accounts data
- iXBRL must start with the exact XML declaration required by the specification
- submissions must be well-formed XML, XHTML and valid iXBRL
- Companies House parses the GovTalk envelope and iXBRL synchronously and rejects invalid submissions before delivery
- the software provider must ensure schema and Companies House business-rule validation before submission

For package accounts:

- UKSEF, Welsh, LP, CIC and exempt-subsidiary package routes use Base64-encoded ZIP packages
- package structure and directory names must follow the TIS
- package size limits and package-specific validation rules apply
- each iXBRL document in a package is validated, and mismatched entity/period/numeric/date content can reject the whole package

For filing authority and eligibility:

- the company authentication code is required as proof of authority to file
- only eligible live companies can file accounts electronically
- accounts must satisfy Companies Act and Companies House validation rules
- accounts supplied should have a maximum of two years of figures
- dormant accounts have additional rules and restrictions
- directors remain responsible for accounts preparation, approval, signature and filing

For testing and imaging:

- software providers are responsible for thoroughly testing before live submissions
- Companies House provides the validator at `https://test-validator.companieshouse.gov.uk/xbrl_validate`
- final rendered accounts images must be readable and conform to industry standards
- the imaging service should be used as part of the development testing process

## Current LedgerHouse Status

### Followed Now

- Companies House public REST API key is resolved from environment/local file and is not exposed in status output.
- Company number input is normalised before lookup.
- Public company profile lookup retrieves company name, status, type, registered office, SIC codes and filing dates.
- Practice users can create/match a LedgerHouse client record from official Companies House public data.
- Audit logging records Companies House profile sync actions.
- The Companies House workspace is staff-only.
- The launch readiness centre marks Companies House filing access as blocked.
- The Companies House workspace now explicitly says accounts filing is not enabled and requires XML Gateway/iXBRL/package filing work.

### Not Applicable To Current Implemented Feature

The following TIS items do not apply to the existing read-only public-data lookup because no accounts submission is sent:

- GovTalk envelope generation
- `<FormSubmission>` XML construction
- Base64 `<Document><Data>` accounts payload
- iXBRL generation
- package ZIP generation
- package directory validation
- Companies House XML Gateway submission
- XML Gateway response polling/handling
- company authentication code use
- presenter filing credentials
- Companies House imaging service
- Companies House accounts validator submission

### Missing Before Accounts Filing Can Be Claimed

Before LedgerHouse can say it follows the TIS for Companies House accounts filing, these must be built and tested:

- secure storage model for presenter credentials and company authentication codes
- explicit client/practice authority and approval workflow before filing
- statutory accounts production model separate from management reports
- iXBRL generation for the supported account categories
- taxonomy selection and validation for the supported filing year/account type
- XHTML/iXBRL rendering checks
- Base64 payload generation
- GovTalk envelope generation
- XML Gateway client
- synchronous rejection/error parsing
- accepted/rejected response handling and audit trail
- Companies House validator integration or documented manual validator run
- imaging-service check or documented equivalent image review
- package ZIP generation if UKSEF, Welsh, LP, CIC or exempt-subsidiary accounts are supported
- tests for company eligibility, company number consistency, two-year figure limits and dormant-account restrictions
- production runbook requiring a controlled test filing before enabling customer filing

## Required Product Boundary

Until the missing filing components are complete, LedgerHouse must describe Companies House functionality as:

> Companies House public company-data lookup and client setup support.

It must not describe the current feature as:

> Companies House accounts filing, electronic filing, XML Gateway filing, iXBRL filing, or package accounts filing.

## Code Changes Made In This Review

- `accounting/companies_house.py`
  - added explicit `filing_enabled=False`
  - added `filing_status`
  - added TIS-specific `filing_detail`
  - added `accounts_tis_version`

- `templates/accounting/companies_house_workspace.html`
  - added accounts filing status
  - added TIS reference
  - added important filing boundary wording

- `accounting/views.py`
  - launch readiness now uses the explicit Companies House filing status/detail

## Decision

The current implementation is acceptable for read-only Companies House public data. It is not yet a Companies House accounts filing implementation. The TIS has been followed where necessary for the current feature by keeping accounts filing disabled and clearly marked as a separate future build.
