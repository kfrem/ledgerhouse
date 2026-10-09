# LedgerHouse HMRC Sandbox Isolation and Local Verification

Date: 2026-08-02

## Scope

This pass was limited to the LedgerHouse project. No files, credentials or
provider records belonging to any other product were edited. All accounting
data used by automated tests and rehearsals was local synthetic data.

## HMRC sandbox activity

The HMRC Developer Hub was opened in the Codex in-app browser and a separate
sandbox application named `LedgerHouse` was created and configured with its
own client secret and local callback URI. The harmless application-restricted
Hello World endpoint was called using that application's own sandbox
credentials.

- Application: LedgerHouse
- Endpoint: `GET /hello/application`
- HTTP status: 200
- Timestamp: 2026-08-02T22:36:41.387Z
- Result: successful sandbox application activity

This report deliberately excludes application identifiers, client IDs, client
secrets, access tokens, OTPs, presenter IDs, authentication values and payloads.
No VAT return, customer-data request or production request was made.

## Changes made in this pass

- `ledgerhouse/settings.py`
  - Added non-secret LedgerHouse application ownership and subscription settings.
- `accounting/mtd.py`
  - Added a sandbox-only Hello World keep-alive function.
  - Removed the legacy mock VAT filing path and made it fail closed.
  - Prevented OAuth authorisation unless the runtime explicitly declares a
    separate LedgerHouse-owned application and VAT subscription.
- `accounting/views.py`
  - Added a local duplicate-submission guard before the HMRC VAT provider call.
- `templates/accounting/hmrc_status.html`
  - Replaced the hard-coded shared-product name and subscription claims with
    LedgerHouse-specific, fail-closed status.
- `accounting/management/commands/hmrc_sandbox_keepalive.py`
  - Added a command that records only redacted keep-alive evidence.
- `accounting/tests/test_hmrc_sandbox.py`
  - Added and updated sandbox, validation, provider-boundary and duplicate
    submission tests.
- `accounting/tests/test_hmrc_sandbox_keepalive_command.py`
  - Added redacted command-output coverage.
- `accounting/tests/test_phase2_3.py`
- `accounting/tests/test_end_to_end.py`
  - Updated obsolete tests so they verify fail-closed behaviour instead of
    depending on fabricated HMRC acceptance.

## Commands run and results

| Command | Result |
| --- | --- |
| `docker compose up -d` | LedgerHouse web and PostgreSQL containers running locally. |
| `docker compose exec -T web python manage.py test --noinput --verbosity 1` (baseline) | PASS: 194 tests in 62.942 seconds. |
| `docker compose exec -T web python manage.py test accounting.tests.test_hmrc_sandbox accounting.tests.test_hmrc_sandbox_keepalive_command --noinput --verbosity 1` | PASS: 28 tests in 4.227 seconds after fixture correction. |
| `docker compose exec -T web python manage.py test accounting.tests.test_phase2_3.Phase2And3Tests.test_hmrc_mtd_vat_legacy_submission_path_fails_closed accounting.tests.test_end_to_end.EndToEndVerificationTests.test_e2e_reconciliation_and_accounting_stages --noinput --verbosity 1` | PASS: 2 tests; six synthetic tenants completed the end-to-end accounting journey. |
| `docker compose exec -T web python manage.py test --noinput --verbosity 1` (final) | PASS: 200 tests in 63.775 seconds. |
| `docker compose exec -T web python manage.py check` | PASS: no issues reported. |
| `docker compose exec -T web python manage.py commercial_readiness_rehearsal --strict --output /tmp/ledgerhouse-commercial-readiness-2026-08-02.md` | PASS: six synthetic tenants passed evidence intake, bank activity, double-entry, reports, production register, practice screen and external-filing safety checks. |
| `docker compose exec -T web python manage.py local_acceptance_suite --strict --output /tmp/ledgerhouse-local-acceptance-2026-08-02.md` | PASS: all local acceptance checks passed, including client/practice pages and CSV, PDF, pack and ZIP outputs. |

## Browser checks

| Route or screen | Result |
| --- | --- |
| HMRC Developer Hub - LedgerHouse sandbox application management | Separate LedgerHouse sandbox application, own secret, Hello World subscription and callback URI verified. |
| HMRC Developer Hub - LedgerHouse redirect URI management | Local callback URI verified. |
| `http://127.0.0.1:8000/integrations/hmrc/` | PASS: page identifies `LedgerHouse`, shows no shared application subscription and disables VAT authorisation until LedgerHouse-owned VAT configuration is explicitly declared. |

## Local work completed

- A real harmless HMRC sandbox application call was completed successfully.
- LedgerHouse no longer presents another product's name or implied API access in
  its HMRC screen.
- The local HMRC OAuth route now fails closed when the runtime lacks explicit
  LedgerHouse ownership and a VAT MTD subscription declaration.
- The legacy mock VAT submission path no longer creates a receipt, a submitted
  status or any accounting side effect.
- A recorded local VAT submission prevents a second provider request for the
  same period.
- Full local regression, acceptance and commercial readiness rehearsals pass.

## Commits

None. The worktree already contained unrelated uncommitted work, so this pass
was deliberately left uncommitted for the project owner to review and group.

## Externally blocked items

1. Configure LedgerHouse's own sandbox client credentials and explicit VAT MTD
   subscription in the local runtime without storing any secret in Git. The new
   LedgerHouse sandbox application currently has Hello World only; it must not
   reuse the existing shared VAT credentials.
2. Obtain the HMRC sandbox VAT test-user authority, VAT registration details and
   required fraud-prevention data, then validate the real VAT OAuth and filing
   route with HMRC. No customer-data or VAT submission has been sent in this pass.
3. HMRC production approval, production credentials and production fraud-
   prevention validation.
4. Companies House live XML gateway validation and provider acceptance for any
   account submissions. Existing local document generation and dry-run records
   are not provider acceptance.
5. Other live integrations such as banking, NEST, payment providers, email,
   DNS and deployment, each requiring its own provider credentials, consent or
   paid-service setup.
