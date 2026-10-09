# LedgerHouse HMRC Sandbox Takeover - 12 August 2026

## Scope

This record covers the LedgerHouse HMRC Developer Hub sandbox configuration and
the local HMRC integration test correction completed on 12 August 2026. It does
not record secrets, client identifiers, OAuth tokens, user credentials, VAT
numbers, or customer data.

## Completed

- Confirmed a separate HMRC sandbox application named `LedgerHouse`.
- Confirmed the sandbox application has an active client secret and redirect
  URI configuration.
- Added and verified the `VAT (MTD) 1.0` sandbox API subscription for
  LedgerHouse only.
- Added the public LedgerHouse privacy and terms URLs to the sandbox customer
  usage information.
- Verified both public policy pages render successfully.
- Added the public HMRC OAuth callback URL alongside the local development
  callback URL, and verified the callback route exists online.
- Replaced the local sandbox client configuration with a newly generated
  LedgerHouse-only sandbox secret. The secret remains only in the ignored local
  `.env` file.
- Performed a harmless authenticated sandbox keep-alive call using the
  LedgerHouse client credentials.
- Added missing PostgreSQL tenant-role grants and row-level security policies
  for HMRC VAT connections and VAT reviews.

## HMRC Sandbox Evidence

| Item | Result |
| --- | --- |
| Application | LedgerHouse sandbox application |
| API subscription | VAT (MTD) 1.0 confirmed subscribed |
| Keep-alive endpoint | `GET /hello/world` |
| HTTP result | `200` |
| Timestamp | 2026-08-12, Europe/London session |
| Secrets or identifiers recorded | No |

## Files Changed

- `accounting/migrations/0028_hmrcvatconnection_rls.py`
- `accounting/migrations/0029_vatreview_rls.py`
- `accounting/middleware.py`
- Local ignored `.env` configuration only; not tracked and not included in this
  report.

## Verification

| Check | Result |
| --- | --- |
| Local Docker image build | Passed |
| Local migrations 0028 and 0029 | Applied successfully |
| Django system check | Passed, no issues |
| Migration drift check | Passed, no changes detected |
| `accounting.tests.test_hmrc_sandbox` | Passed: 27 tests |
| Browser: `/privacy/` | Passed |
| Browser: `/terms/` | Passed |
| Browser: `/api/integrations/hmrc/callback` | Passed: route reached and returned expected HMRC authorisation response |

## Correction Made

The initial focused suite found that the PostgreSQL restricted tenant role did
not have permissions or row-level policies for `HmrcVatConnection` and
`VatReview`. This caused tenant-scoped VAT workflows to fail in PostgreSQL even
though the application started. Migrations 0028 and 0029 give both tables the
same tenant-bound access model used by the rest of LedgerHouse. The complete
focused HMRC suite passed after the correction.

The tenant reset helper was also changed so an already-aborted Django test
transaction is not masked by a second cleanup error. Django rolls that test
transaction back before reuse.

## Production Deployment Follow-up - 13 August 2026

The two tenant-isolation migrations and middleware correction were deployed to
the intended LedgerHouse service. A dated pre-change server backup was retained
under the LedgerHouse server directory before replacement.

The service restart completed with the following results:

| Check | Result |
| --- | --- |
| Migrations 0028 and 0029 | Applied |
| Production Django check | Passed with no issues |
| Internal health endpoint | Passed: `status: ok` |
| Public health endpoint | Passed: `status: ok` |
| Runtime database container | Healthy |
| Runtime web container | Healthy |
| Django production secret | Replaced with a new server-only random value |

Rotating the production Django secret invalidates existing LedgerHouse web
sessions. It does not alter accounting records, database data, provider
credentials or filing state.

## Tenant Isolation Completion - 13 August 2026

The wider clean-stack regression exposed further PostgreSQL tenant-role gaps in
newer LedgerHouse tables. These were corrected before production deployment.
The corrections are designed to fail closed: the restricted runtime role only
has access to rows inside the active tenant context, except for the controlled
global Companies House submission sequence used to allocate unique submission
numbers.

### Additional Files Changed

- `accounting/migrations/0030_complete_tenant_table_rls.py`
- `accounting/migrations/0031_tenant_user_access_rls.py`
- `accounting/migrations/0032_companies_house_sequence_grant.py`
- `accounting/companies_house_scenarios.py`
- `accounting/views.py`

### Local Regression Evidence

| Check | Result |
| --- | --- |
| HMRC sandbox focused suite | Passed: 27 tests |
| Client portal and accounts-department focused suite | Passed: 44 tests |
| Companies House controlled local scenario suite | Passed: 41 tests |
| Complete Docker test suite | Passed: 206 tests in 65.512 seconds |

The Companies House tests use synthetic local records and controlled dry-run
scenarios. They do not represent a live gateway filing or Companies House
acceptance.

### Live Deployment Evidence

| Check | Result |
| --- | --- |
| Migrations 0030, 0031 and 0032 | Applied successfully |
| Restricted runtime Django production check | Passed with no issues |
| Internal health endpoint | Passed: `status: ok` |
| Public health endpoint | Passed: `status: ok` |
| Runtime web container | Running |
| Runtime database container | Healthy |
| Public login route | Returned HTTP 200 |
| Public privacy route | Returned HTTP 200 |

The owner-role warning shown during migration execution is expected because
migrations must run with database-owner privileges. The normal LedgerHouse web
container was separately checked after deployment using its restricted runtime
role and reported no warnings or errors.

## Remaining Provider Boundary

The separate LedgerHouse production credentials request remains with HMRC as
`Credentials requested`; HMRC states that review can take at least 10 working
days. No live VAT return was submitted. Live VAT filing remains disabled until
HMRC production credentials are issued, the production application is
configured, a customer authorises LedgerHouse, and the live transport plus
fraud-prevention headers are validated.
