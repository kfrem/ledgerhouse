# HMRC access request - LedgerHouse tax services

**Status:** Prepared locally; not yet sent  
**Date:** 24 August 2026

## Verified position before sending

| Service | HMRC route | Current evidence | Action requested from HMRC |
|---|---|---|---|
| VAT Making Tax Digital | REST API with OAuth | Developer Hub displays `Credentials requested`; HMRC acknowledgement dated 13 July 2026, reference `2026-VXY565` | Continue the existing review; do not create a duplicate request |
| Corporation Tax Online | XML API | Local CT600 preparation and validation controls built; no HMRC XML test acceptance | Register LedgerHouse for XML development and issue the required test route/material |
| PAYE/RTI Online | XML API | Local FPS/EPS preparation and validation controls built; no HMRC XML test acceptance | Register LedgerHouse and provide RTI testing requirements and credentials |
| Construction Industry Scheme Online | XML API | Local CIS300 preparation and validation controls built; no HMRC XML test acceptance | Register LedgerHouse and provide CIS testing requirements and credentials |
| Self Assessment Online | XML API | Local SA100/SA800/SA900 preparation and validation controls built; no HMRC XML test acceptance | Register LedgerHouse and confirm the return types and tests required |
| Income Tax Making Tax Digital | REST APIs with OAuth | Local quarterly/annual preparation and validation controls built; no production subscription | Confirm the next onboarding window and the sandbox/API subscriptions available now |

## Email ready to send

**Subject:** LedgerHouse XML software registration and test credentials

Dear Software Developer Support Team,

KAFS Limited, trading as KAFS Automation, is developing LedgerHouse, a
commercial accounting and accounts-department software product.

Please register LedgerHouse for development and testing of these HMRC XML
services:

- Corporation Tax Online, including CT600 returns and amendments
- PAYE/RTI Online, including FPS and EPS submissions
- Construction Industry Scheme Online, including CIS300 returns
- Self Assessment Online, including SA100, SA800 and SA900 returns

Company name: KAFS Limited, trading as KAFS Automation  
Product name: LedgerHouse  
Contact name: Godfred Frimpong  
Contact email: info@kafs-ltd.com

KAFS Limited has previously been registered as an HMRC software developer.
Please associate these XML services with our existing registration and Vendor
ID where appropriate rather than creating a duplicate registration. Please
provide or confirm the Vendor ID, service registrations and test credentials
required to access the External Test Service for the XML services listed above.

Our separate VAT MTD production-credential request is already under review as
reference `2026-VXY565`; this email does not ask HMRC to create a duplicate VAT
request. Income Tax MTD will continue through our existing LedgerHouse
Developer Hub application and is not part of this XML registration request.

We will not use live services for testing and will keep every filing route
disabled until the relevant HMRC testing and approval have been completed.

Kind regards,

Godfred Frimpong  
Software Development Officer  
KAFS Limited, trading as KAFS Automation

## Sending control

Attach no credentials, tokens, taxpayer references, client records or filing
payloads.
