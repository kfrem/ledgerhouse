# LedgerHouse HMRC Two-Track Completion Report

**Date:** 24 August 2026  
**Scope:** Income Tax MTD/API preparation and HMRC XML Transaction Engine
preparation. No production filing was made.

## Completed locally

- Added an Income Tax MTD API coverage register for the in-year and end-of-year
  product journeys.
- Added staff-visible subscription status for Business Details, Obligations,
  Self Employment, Property, BSAS, Losses, Tax Liability Adjustments,
  Calculations, Test Support and Fraud Prevention Headers.
- Added a versioned REST call boundary that requires a user token, fraud
  prevention headers, a valid API version and a safe endpoint path.
- Prevented `Gov-Test-Scenario` from being sent outside the sandbox.
- Added separate local preparation journeys for quarterly updates, annual
  summaries, SA100, SA800 and SA900.
- Added HMRC Transaction Engine submission and polling envelope generation.
- Added generic IRmark generation using canonical XML, SHA-1 and Base64 over
  the HMRC `Body`, excluding the `IRmark` element.
- Added filing profiles for CT600/amendments, FPS, EPS, CIS300, SA100, SA800
  and SA900.
- Added Transaction Engine response parsing for pending, accepted and rejected
  outcomes.
- Added fail-closed network transport for HMRC sandbox and production URLs.
- Added verified-response-only status transitions, encrypted provider response
  storage, retry idempotency and protection against overwriting final provider
  decisions.
- Extended the redacted HMRC evidence register with Income Tax API subscription
  coverage.

## Integrity boundary

The generic XML layer wraps and transmits a service body; it does not invent an
HMRC CT600, RTI, CIS or Self Assessment return body. Each body must still be
generated from the current official HMRC schema/RIM pack and pass LTS/ETS and
HMRC recognition testing. Transport remains disabled until that evidence and
the HMRC-issued XML test credentials exist.

Income Tax MTD API versions and subscriptions change independently. The
workspace records the versions reviewed on 24 August 2026. HMRC's current API
pages warn that new production credential applications for 2026-27 quarterly
update products are no longer being accepted; this does not prevent continued
sandbox and end-of-year development, but it is a production constraint.

## Tests and exact results

1. Baseline HMRC tests before editing: `44` tests passed.
2. First protocol run: `12` tests; `11` passed and `1` assertion failed because
   the test rejected every IRmark instead of only an empty IRmark.
3. The assertion was corrected to parse the XML and verify a 28-character
   generated mark. No production rule was weakened.
4. Repeated protocol run: `12` tests passed.
5. Integrated HMRC service, XML and Income Tax run: `24` tests passed; system
   check passed; no migration drift.
6. Provider result controls added and retested: `26` tests passed.
7. Full regression: `257` tests passed in `66.961` seconds; system check passed.
8. Final focused verification after UI and documentation corrections: `58`
   HMRC tests passed in `5.863` seconds; system check passed; no migration drift.
9. Second full regression: `257` tests passed in `82.869` seconds.
10. Final independent HMRC verification: `26` tests passed in `1.609`
    seconds; system check passed with no issues.

## Browser checks

Route: `http://127.0.0.1:8000/integrations/hmrc/services/`

- Desktop DOM confirmed six service families and ten Income Tax API rows.
- The first browser pass found the API checklist incorrectly nested in the
  sidebar. The template was corrected and rechecked.
- Corrected structure: no headings remained in the sidebar and all workspace
  sections rendered under `main`.
- Mobile `390 x 844`: no page overflow, button overflow or table overflow.
- Browser console: no warnings or errors.
- SA800 draft created a validation-failed case with three explicit blockers.
- Income Tax annual draft created a validation-failed case with six blockers.
- Neither action created a provider receipt or submission result.

## Redacted evidence

- `output/hmrc/ledgerhouse_hmrc_application_evidence.md`
- Tokens, passwords, taxpayer references, client identifiers and filing
  payloads are excluded.

## External actions still required

- The existing VAT production credential request remains with HMRC; do not
  create a duplicate.
- Developer Hub sign-in is required to add or verify the Income Tax MTD API
  subscriptions. The browser session had expired during this pass.
- HMRC SDST must issue or confirm XML Vendor ID and test credentials for CT600,
  FPS/EPS, CIS300 and SA100/SA800/SA900.
- Current official service schema/RIM packs and HMRC recognition scenarios must
  pass LTS/ETS. Local tests are not HMRC acceptance.
- HMRC must grant production credentials and the client must authorise filing
  before any live submission.

## Official references

- https://www.gov.uk/guidance/basic-guide-for-xml-software-developers
- https://www.gov.uk/government/collections/register-as-a-software-developer
- https://www.gov.uk/government/publications/hmrc-irmark-generic-irmark-specification
- https://developer.service.hmrc.gov.uk/guides/income-tax-mtd-end-to-end-service-guide/
- https://developer.service.hmrc.gov.uk/guides/vat-mtd-end-to-end-service-guide/
