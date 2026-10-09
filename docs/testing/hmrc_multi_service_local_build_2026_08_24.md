# LedgerHouse HMRC Multi-Service Local Build Report

**Date:** 24 August 2026  
**Scope:** Local preparation and approval-readiness work only. This report does
not claim HMRC production approval or provider acceptance.

## Completed locally

- Added a separate approval register for VAT MTD, Corporation Tax Online, PAYE
  Online/RTI, CIS Online, Income Tax MTD and Self Assessment Online.
- Recorded the correct transport boundary: VAT/Income Tax MTD use REST with
  OAuth; Corporation Tax, PAYE RTI, CIS and Self Assessment use the HMRC XML
  Gateway routes.
- Added tenant-scoped encrypted HMRC tax profiles and encrypted filing payloads.
- Added filing cases with local validation results, dual-approval fields,
  unique idempotency keys, encrypted provider evidence fields and provider
  decision timestamps.
- Added local validators for CT600 and amendments, FPS, EPS, CIS300, Income Tax
  MTD quarterly/annual data, and SA100/SA800/SA900 declarations.
- Added a staff-only HMRC service workspace with secure tax-reference updates,
  service status, official documentation links, filing preparation and
  repeatable preflight checks.
- Added preparation routes for CT600, FPS, EPS, CIS300, Income Tax MTD and
  SA100. Incomplete cases expose precise blockers rather than fabricating data.
- Added a redacted application-evidence command covering every service's local
  pass/fail totals, approval status, request date and official documentation.
- Direct mailbox verification on 24 August 2026 found HMRC's acknowledgement
  of the LedgerHouse production application credential request. It was received
  on 13 July 2026 at 22:39 Europe/London under support reference `2026-VXY565`.
  HMRC stated that the request had been received and would be reviewed as soon
  as possible. Its accompanying delay notice referred specifically to a high
  volume of Making Tax Digital for Income Tax enquiries, so it is not evidence
  of a VAT-specific processing delay.
- A direct Developer Hub check on 24 August confirmed that the separate
  LedgerHouse production application remains at `Credentials requested` and
  subscribes to VAT (MTD). No credential value was copied into the tracker or
  report.
- Verified the separate LedgerHouse sandbox application has VAT (MTD) 1.0 and
  Hello World 1.0 subscriptions, configured redirect URIs and active client
  secrets.
- Called the harmless LedgerHouse sandbox Hello World application endpoint.
  HMRC returned HTTP 200 at `2026-08-24T08:14:37.551447+00:00`, and the
  Developer Hub subsequently displayed `Last API call 24 August 2026`.
- Added PostgreSQL row-level security policies for tenant tax profiles and
  filing cases, plus restricted-role grants for all new tables.
- Kept all multi-service submissions fail closed. No local action can create a
  provider receipt, correlation ID, accepted status or accounting side effect.

## Files changed for this work

- `accounting/models.py`
- `accounting/hmrc_services.py`
- `accounting/views.py`
- `accounting/admin.py`
- `accounting/migrations/0034_hmrcserviceapproval_hmrctaxprofile_hmrcfilingcase.py`
- `accounting/tests/test_hmrc_services.py`
- `accounting/management/commands/build_hmrc_application_evidence.py`
- `ledgerhouse/urls.py`
- `templates/accounting/hmrc_services_workspace.html`
- `templates/accounting/hmrc_status.html`
- `static/accounting/dashboard.css`
- `README.md`
- `DEPLOYMENT.md`

## Commands and exact results

1. `docker compose up -d --build`
   - Stack built and started.
2. `docker compose exec -T web python manage.py migrate`
   - Migration `accounting.0034` applied successfully.
3. First focused test run
   - 9 tests discovered; 6 passed and 3 errored because the restricted tenant
     role lacked access to the global HMRC approval table.
   - The migration was corrected to grant the required access; no test was
     weakened or removed.
4. `docker compose exec -T web python manage.py test accounting.tests.test_hmrc_services -v 2`
   - Final focused run: 12 tests run; all passed.
5. `docker compose exec -T web python manage.py makemigrations --check`
   - No changes detected.
6. `docker compose exec -T web python manage.py check`
   - System check identified no issues.
7. `docker compose exec -T web python manage.py build_hmrc_application_evidence`
   - Redacted evidence written to
     `output/hmrc/ledgerhouse_hmrc_application_evidence.md`.
8. `curl.exe -s -o NUL -w "health=%{http_code}" http://127.0.0.1:8000/healthz/`
   - `health=200`.
9. Final `docker compose exec -T web python manage.py test -v 1`
   - 231 tests run in 67.191 seconds; all passed.
10. `docker compose exec -T web python manage.py shell -c "...call_hmrc_sandbox_keepalive()..."`
    - LedgerHouse sandbox `GET /hello/application` returned HTTP 200.
    - Redacted timestamp: `2026-08-24T08:14:37.551447+00:00`.
    - No token, client ID or client secret was written to this report.
11. Direct HMRC Developer Hub browser verification
    - LedgerHouse production status: `Credentials requested`.
    - Production API subscription: VAT (MTD).
    - Separate LedgerHouse sandbox subscriptions: VAT (MTD) 1.0 and Hello
      World 1.0.
    - Sandbox activity row: `LedgerHouse 24 August 2026`.
12. `docker compose exec -T web python manage.py build_hmrc_application_evidence`
    - Rebuilt the redacted evidence register after direct portal verification.
13. `docker compose exec -T web python manage.py test accounting.tests.test_hmrc_sandbox accounting.tests.test_hmrc_sandbox_keepalive_command accounting.tests.test_hmrc_services -v 1`
    - 40 tests run in 5.577 seconds; all passed.
14. `docker compose exec -T web python manage.py check`
    - System check identified no issues.
15. `docker compose exec -T web python manage.py makemigrations --check`
    - No model changes detected.

## Browser verification

Route checked:
`http://127.0.0.1:8000/integrations/hmrc/services/`

- Confirmed all six service families render with distinct transports, filing
  types and approval states.
- Confirmed existing encrypted references are not displayed in the browser.
- Created an SA100 local draft for the synthetic CareCo tenant.
- Confirmed the case remained `Validation failed`, listed three precise
  blockers and did not show any provider receipt or submission result.
- Confirmed six service rows in the rendered DOM.
- Checked a 390 x 844 mobile viewport: no horizontal page overflow; headings,
  navigation, client selector and reference fields remained usable.
- Browser console: zero warnings and zero errors.

HMRC Developer Hub routes checked in the Codex in-app browser:

- Applications list: confirmed distinct LedgerHouse production and sandbox
  applications; no other product was changed.
- LedgerHouse production request: confirmed `Credentials requested`, VAT (MTD)
  subscription and the stated review boundary of at least 10 working days.
- LedgerHouse sandbox details: confirmed Sandbox environment, VAT (MTD) 1.0,
  Hello World 1.0, redirect URI configuration and client-secret presence.
- LedgerHouse sandbox client-secret page: confirmed two existing secrets; no
  secret was displayed, copied, generated, rotated or deleted.
- Applications list after the keep-alive: confirmed HMRC recorded the last API
  call as 24 August 2026.

## Security and integrity checks

- Raw PostgreSQL reads confirmed that tax references and filing payload values
  are not stored as plaintext.
- Tenant-scoped browser and integration tests confirmed one client's filing
  cases are not rendered in another client's selected workspace.
- Client users are redirected away from the practice-only HMRC workspace.
- Invalid filing type/service combinations fail preflight.
- A valid local case moves only to `Ready for approval`, never to submitted.
- Even after simulated dual local approval, provider transport remains locked.

## Externally blocked only

- HMRC production-credential review for LedgerHouse VAT MTD is still awaiting
  HMRC's decision; a Developer Hub login is not approval.
- Corporation Tax Online needs HMRC XML Gateway registration, official test
  material/schema conformance and provider acceptance before transport can be
  enabled.
- PAYE Online/RTI needs HMRC-recognised FPS/EPS testing, employer authority and
  production credentials.
- CIS Online needs the relevant HMRC XML testing/credentials and real
  subcontractor-level records.
- Income Tax MTD needs the relevant API subscriptions, OAuth scopes, individual
  authority and official sandbox journey testing.
- Self Assessment Online needs the applicable XML test route, return-type
  coverage, taxpayer declaration/authority and production credentials.

These blockers do not prevent further accounting product work. They do prevent
truthful claims of live HMRC filing for the affected service.
