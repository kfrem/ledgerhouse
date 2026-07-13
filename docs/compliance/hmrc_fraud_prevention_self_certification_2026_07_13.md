# HMRC Fraud Prevention Self-Certification Evidence

Date: 2026-07-13

Software: LedgerHouse / KAFS UK Accounting SaaS.

## Scope

This record supports the HMRC Developer Hub fraud-prevention checklist answer for the production credentials request.

## HMRC Requirement

HMRC requires fraud-prevention HTTP headers for VAT (MTD) and other covered APIs. For LedgerHouse's SaaS architecture, the relevant connection method is **web application via server**.

Primary HMRC references reviewed:

- HMRC fraud prevention guide: `https://developer.service.hmrc.gov.uk/guides/fraud-prevention/`
- HMRC web application via server header specification: `https://developer.service.hmrc.gov.uk/guides/fraud-prevention/connection-method/web-app-via-server/`

## Implementation

LedgerHouse now builds and submits the web-app-via-server header set for HMRC VAT API calls:

- `Gov-Client-Connection-Method: WEB_APP_VIA_SERVER`
- `Gov-Client-Browser-JS-User-Agent`
- `Gov-Client-Device-ID`
- `Gov-Client-Multi-Factor`
- `Gov-Client-Public-IP`
- `Gov-Client-Public-IP-Timestamp`
- `Gov-Client-Public-Port`
- `Gov-Client-Screens`
- `Gov-Client-Timezone`
- `Gov-Client-User-IDs`
- `Gov-Client-Window-Size`
- `Gov-Vendor-Forwarded`
- `Gov-Vendor-License-IDs`
- `Gov-Vendor-Product-Name`
- `Gov-Vendor-Public-IP`
- `Gov-Vendor-Version`

Code evidence:

- `accounting/mtd.py`: `build_web_app_via_server_fraud_prevention_headers`.
- `accounting/views.py`: HMRC VAT sync, submit and retrieve calls pass `fraud_headers`.
- `static/accounting/fraud_context.js`: collects browser user agent, persistent device ID, screen details, timezone and window size.
- `templates/accounting/hmrc_vat_workspace.html`: HMRC sync/submit forms include fraud-context fields.
- `ledgerhouse/settings.py`: `HMRC_VENDOR_PUBLIC_IP` and `HMRC_VENDOR_VERSION` are environment-configurable.

## Test Evidence

- `accounting.tests.test_hmrc_sandbox`: 22 tests OK on 2026-07-13.
- Specific tests prove:
  - web-app-via-server fraud header builder includes the expected HMRC header set;
  - VAT obligations sync passes `WEB_APP_VIA_SERVER` headers;
  - VAT return submission passes `WEB_APP_VIA_SERVER` headers;
  - the HMRC Test Fraud Prevention Headers validator endpoint is called with the generated headers.
- Live HMRC sandbox validator result on 2026-07-13:
  - endpoint: `https://test-api.service.hmrc.gov.uk/test/fraud-prevention-headers/validate`
  - `specVersion`: `3.3`
  - `code`: `VALID_HEADERS`
  - message: all headers required for the connection method were supplied and appeared valid.
- Full suite after fraud-prevention implementation: 101 tests OK on 2026-07-13.
- Migration check: no changes detected.
- Django system check: no issues.

## Production Conditions

Before production use with external customers:

- Set `HMRC_VENDOR_PUBLIC_IP` to the real public IP or public ingress address used for HMRC-bound requests.
- Set `HMRC_VENDOR_VERSION` to the released product version.
- Ensure the reverse proxy/load balancer passes the real originating client IP and port where available.
- Maintain the browser-side fraud context script on HMRC submission pages.

On that basis, the current controlled application has a defensible basis to answer **Yes** to HMRC's question that the software submits fraud-prevention data.
