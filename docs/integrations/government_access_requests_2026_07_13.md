# Government access requests - 2026-07-13

## HMRC Developer Hub

Application: `KAFS UK Accounting SaaS`

Progress made:

- Signed in to HMRC Developer Hub as Godfred Frimpong.
- Started the production credentials request for the valid sandbox application.
- Confirmed the software is sold/resold/distributed.
- Confirmed the production API scope as `VAT (MTD) - 1.0`.
- Reached the terms-of-use checklist.
- Completed the first organisation-detail answer: Godfred is the responsible individual.
- Entered organisation/product URL: `https://ledgerhouse.finaccord.pro`.

Current blocker:

- HMRC requires one organisation identity evidence option:
  - Unique Taxpayer Reference (UTR)
  - VAT registration number
  - Corporation Tax UTR
  - PAYE reference
  - or a declaration that the UK organisation has none of these

No value was entered for this step because none of those tax identifiers is stored in this project, and selecting "does not have any" for a UK limited company would be a factual declaration that must not be invented.

Next action:

- Provide the correct KAFS LIMITED tax identifier, preferably Corporation Tax UTR if the company is applying as a limited company.
- Then resume the HMRC production credentials checklist.

## Companies House Developer Hub

Existing app: `Practice App`

Progress made:

- Confirmed the existing live REST API key remains available for public Companies House data.
- Confirmed Developer Hub only exposes REST API key management for this app; it does not issue software filing presenter credentials from the app page.

## Companies House presenter account

Progress made:

- Used the official GOV.UK presenter-account route for no-fee software filing.
- Looked up the registered business using the Companies House API.
- Confirmed active company:
  - `KAFS LIMITED`
  - company number `06762730`
  - incorporated `2 December 2008`
- Submitted the presenter-account application with:
  - contact name: Godfred Frimpong
  - correspondence address: KAFS LIMITED registered office, `5 Brayford Square, London, United Kingdom, E1 0SG`

Result:

- Companies House accepted the application.
- Confirmation page says they will create the presenter account and email `kfrem@hotmail.com` with:
  - presenter ID
  - presenter code
- Expected time: up to 1 hour.

Next action:

- Check `kfrem@hotmail.com` inbox and junk folder for the Companies House presenter ID and presenter code.
- Store them locally outside Git when received.

## Companies House credit account

Reason needed:

- Presenter account covers company accounts and documents with no filing fee.
- Fee filings such as incorporations and confirmation statements require a Companies House credit account.

Progress made:

- Opened the official GOV.UK credit-account route.
- Downloaded and inspected the credit-account application PDF.

Current blocker:

- This is not an online submission flow. The form must be completed and sent to `chdfinance@companieshouse.gov.uk`.
- The form requires information that is not available in this repo and must not be invented:
  - annual turnover
  - number of employees
  - trading status and main business activity confirmation
  - existing Companies House customer account details, if any
  - electronic invoice delivery email shared by more than one person
  - full user contact details and telephone/fax where applicable
  - whether WebFiling, software filing, or both are required
  - two trade references if not applying as an individual
  - expected monthly business value
  - payment option / direct debit or card account handling
  - authorised signature and date

Next action:

- Complete the credit-account PDF with verified business/finance details and signature.
- Email it to `chdfinance@companieshouse.gov.uk`.
- Expected processing time from GOV.UK guidance: up to 5 days.

## Sources

- GOV.UK: Apply to file with Companies House using software
- GOV.UK: Apply for a Companies House credit account
- HMRC Developer Hub production credentials flow
