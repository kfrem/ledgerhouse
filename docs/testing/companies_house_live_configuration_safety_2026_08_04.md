# Companies House Live Configuration Safety Report - 2026-08-04

## Purpose

Prepare LedgerHouse's local production configuration for the Companies House
live package without transmitting a live filing or exposing any credential.

## Completed locally

- Created a LedgerHouse-only local credential file in the Git-ignored
  `.secrets` directory.
- Restricted the credential directory and file to the logged-in Windows user
  and `SYSTEM` using explicit ACLs.
- Added the LedgerHouse live package configuration with gateway test mode set
  to live (`0`) and live sending locked (`False`).
- Added a separate release-manager environment gate. It remains `False`.
- Removed test-mode default values that could override a secure credential
  file in production.
- Added a read-only secret mount to `docker-compose.prod.yml`.
- Added a live submission entry point which fails closed unless all release,
  client-authorisation and filing-readiness controls are satisfied.
- Updated deployment guidance for securely placing the ignored secret file on
  the production server.

## Files changed

- `ledgerhouse/settings.py`
- `accounting/companies_house.py`
- `accounting/tests/test_companies_house.py`
- `docker-compose.prod.yml`
- `DEPLOYMENT.md`
- `.env` (ignored local configuration; not committed)
- `.secrets/companies_house_ledgerhouse_live.env` (ignored local credential
  file; not committed and not reproduced here)

## Commands and results

| Command or check | Result |
| --- | --- |
| Host test discovery | Initially blocked because host Django could not resolve Docker database host `db`; no product defect identified. |
| `docker compose up -d --build db web` | Passed. Docker database and web services started. |
| `docker compose exec -T web python manage.py test accounting.tests.test_companies_house --verbosity 1` | Initially exposed a boolean/text configuration defect. Corrected in `accounting/companies_house.py`. Final result: 41 tests passed. |
| `docker compose exec -T web python manage.py test --verbosity 1` | Passed: 206 tests completed in 67.051 seconds with no failures or Django system-check issues. |
| Local Companies House scenario dry-runs | Passed. Each remained clearly marked `Not allocated` and `Not sent`; no provider transport occurred. |
| `docker compose exec -T web python manage.py check --database default` | Passed with no Django system-check issues. |
| Live credential resolution and send-lock check | Passed. Public status identifies locked live credentials without exposing credential material; a live submission is rejected before any outbound call while the release gate is disabled. |
| `docker compose -f docker-compose.prod.yml config --quiet` | Passed. Production Compose configuration renders with the read-only LedgerHouse secret mount. |
| `curl.exe -fsS http://127.0.0.1:8000/healthz/` | Passed: local Docker web service returned `{"status": "ok"}` while the database service was healthy. |
| `git diff --check` | Passed with no whitespace errors. Existing line-ending notices apply to the pre-existing dirty worktree. |

## Safety controls verified

- Test submission code refuses credentials configured with live test flag `0`.
- Live submission code refuses test credentials.
- Live submission code requires written approval configuration, an explicit
  release-manager enablement, a client Companies House authentication code,
  an identified operator and the existing filing readiness checks.
- API response, correlation and receipt fields continue to be sanitised before
  they are stored or displayed.
- No credential, presenter identifier, authentication value, package reference
  or client data is included in this report, source code, Git configuration or
  test output.

## Provider boundary

No live Companies House request was made. This is intentional: Companies House
does not permit testing in the live service, and no authorised client filing
with explicit approval was supplied for this work.

## Remaining external release actions

1. Copy the ignored LedgerHouse secret file to the server using the procedure
   in `DEPLOYMENT.md`, with the same owner-only permissions.
2. Deploy the production Compose stack and complete HTTPS, backup, monitoring
   and server smoke checks.
3. For the first authorised client filing, obtain the company authentication
   code and documented approval, then enable the release-manager switch for
   that controlled release.
4. Monitor the provider response and treat any live rejection as a real
   validation outcome; do not retry by creating a false accepted record.
