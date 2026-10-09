# LedgerHouse HMRC Current Status and Actions

**Date:** 21 September 2026  
**Scope:** Read-only Developer Hub inspection, fresh sandbox activity, local
verification and follow-up preparation. No tax filing or production credential
change was made.

## Verified Developer Hub position

| Item | Verified status |
|---|---|
| LedgerHouse production request | `Credentials requested`; HMRC review remains pending |
| Production API scope requested | VAT (MTD) only |
| LedgerHouse sandbox application | Exists separately and is active |
| Sandbox subscriptions | VAT (MTD) 1.0 and Hello World 1.0 |
| Client credentials | Client ID exists; two client-secret records are present; values not recorded here |
| Redirect URIs | Two configured; values not recorded here |
| Previous Hub activity | 24 August 2026 |
| Fresh application activity | Successful `GET /hello/application`, HTTP 200, 21 September 2026 |

## Checklist disposition

1. **Chase HMRC directly - COMPLETED**
   - The production request was submitted on 13 July 2026.
   - HMRC's current Developer Hub guidance says the production check takes up
     to 10 working days.
   - The request remains pending, so a status follow-up is justified.
   - The follow-up was submitted through the official Developer Hub support
     form on 21 September 2026. HMRC confirmed submission, confirmation-email
     dispatch and a reply target of two UK business days.
   - The submitted wording and evidence are stored at
     `docs/correspondence/hmrc_vat_production_review_follow_up_2026_09_21.md`.

2. **Keep the sandbox active and polished - COMPLETE FOR THIS PASS**
   - A harmless LedgerHouse-owned Hello World application call succeeded.
   - The current keep-alive evidence is
     `docs/testing/hmrc_sandbox_keepalive_latest.md`.
   - VAT obligation retrieval, return retrieval, return submission mapping,
     OAuth code exchange, refresh/error boundaries and fraud-prevention header
     handling are implemented and covered by automated tests.

3. **Compliance documentation - COMPLETE LOCALLY, EXTERNAL REVIEW REMAINS**
   - Technical and plain-English production credential evidence packs exist.
   - Privacy and terms routes are published and recorded in the Hub.
   - Self-certification records cover accessibility, personal data, software
     security, service management, customer authorisation and fraud prevention.
   - Automated evidence does not replace an independent legal review or a
     current independent penetration test report.

4. **Prepare the next scopes - LOCAL PREPARATION COMPLETE; ONBOARDING BLOCKED**
   - Local preparation exists for Income Tax MTD, CT600/amendments, FPS, EPS,
     CIS300, SA100, SA800 and SA900.
   - The current Developer Hub production request does not include these
     services.
   - XML services require HMRC registration, official schema/RIM packs, test
     credentials and provider acceptance. Income Tax MTD requires the relevant
     API subscriptions and onboarding window.
   - The consolidated access request is prepared at
     `docs/correspondence/hmrc_all_tax_services_access_request_2026_08_24.md`.

5. **Build the product while waiting - SUBSTANTIALLY COMPLETE AND VERIFIED**
   - Client onboarding, tenant access, evidence intake, reporting, VAT review,
     practice workflows, period end, approvals, audit history and local filing
     preparation are implemented.
   - External payment-provider activation, independent legal review and live
     HMRC customer authorisation remain external release gates.

## Commands and exact results

```text
docker compose up -d
PASS - PostgreSQL healthy and LedgerHouse web container started

docker compose exec -T web python manage.py check
PASS - System check identified no issues (0 silenced)

docker compose exec -T web python manage.py makemigrations --check --dry-run
PASS - No changes detected

docker compose exec -T web python manage.py test \
  accounting.tests.test_hmrc_sandbox \
  accounting.tests.test_hmrc_sandbox_keepalive_command \
  accounting.tests.test_hmrc_services \
  accounting.tests.test_hmrc_income_tax \
  accounting.tests.test_hmrc_xml --noinput
PASS - 59 tests in 7.028 seconds

docker compose exec -T web python manage.py hmrc_sandbox_keepalive
PASS - HTTP 200; redacted evidence written

docker compose exec -T web python manage.py test --noinput
PASS - 257 tests in 97.549 seconds
```

## Honest release boundary

The successful sandbox call proves the LedgerHouse sandbox credentials and
Hello World integration are active. The tests prove the current local code
passes its automated suite. Neither result grants production access or proves a
real VAT filing. Live VAT filing must remain disabled until HMRC approves the
production application, production credentials are configured outside Git, a
controlled customer authorises LedgerHouse, and the controlled live release
gate is completed.
