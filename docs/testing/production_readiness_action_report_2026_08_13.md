# LedgerHouse Production-Readiness Action Report

Date: 13 August 2026

## Actions Completed

1. **Backups and restore**: verified the nightly server backup timer is enabled
   and active. A fresh backup was restored into an isolated temporary PostgreSQL
   container. The restore contained 53 application tables and tenant data; the
   temporary container and temporary restore artefacts were removed afterwards.
2. **Service monitoring**: installed `ledgerhouse-healthcheck.timer`, running
   every five minutes. Its first health probe passed. The existing service
   restart policy remains in place.
3. **Legal preparation**: created `docs/legal/LEGAL_REVIEW_BRIEF_2026_08_13.md`
   for an independent UK legal/commercial review. Public privacy and terms
   routes already exist; this is not a claim of legal sign-off.
4. **Email delivery boundary**: verified that LedgerHouse currently records
   notification attempts but does not claim external email delivery. No email
   provider account or sending-domain configuration was found.
5. **Payment boundary**: verified that subscription records support manual,
   Stripe and GoCardless states, but there is no configured live payment
   provider, webhook secret or provider verification.
6. **Bank-feed boundary**: verified that current bank-feed sync is a local
   demonstration provider only. It cannot contact a real bank and remains
   fail-closed until a contracted provider and client consent journey exist.
7. **HMRC**: verified the installed LedgerHouse application is configured for
   sandbox only. No HMRC production credential or client OAuth authority was
   verified and no HMRC action was sent.
8. **Companies House**: installed the protected LedgerHouse credential file on
   the server as a read-only runtime mount; corrected the compose mount path;
   enabled the approved live-package gate; and retained the independent
   submission-send switch as disabled. No Companies House filing was sent.
9. **Pilot UAT**: created `docs/testing/pilot_uat_plan_2026_08_13.md` covering
   client, practice, month-end, approval and accounts-readiness journeys.

## Security Corrections

- Rotated the production application signing key and restarted the web service.
- Retained dated server-side copies before each configuration change.
- All credential verification was metadata-only; this report contains no
  credentials, tokens, client authentication codes or filing data.

## Verification Results

| Check | Result |
| --- | --- |
| Focused Companies House, launch and deployment tests | Passed: 76 tests |
| Final complete LedgerHouse regression | Passed: 219 tests in 60.307 seconds |
| Docker compose configuration validation | Passed |
| Live Django deployment check | Passed with no errors |
| Live health endpoint | Passed |
| Nightly backup timer | Enabled and active |
| Isolated production-backup restore | Passed: 53 tables and tenant records restored |
| Five-minute health timer | Enabled, active and first probe passed |
| Companies House live credential visibility | Passed: credential file visible to the non-root LedgerHouse runtime |
| Companies House send safety | Passed: live send remains disabled |

## Externally Blocked Items

1. **Encrypted off-server backup copy and alert destination**: the host retains
   verified local backups, but an external storage/monitoring provider is not
   configured.
2. **Legal sign-off**: a qualified adviser must approve the customer terms,
   privacy notice and data-processing position.
3. **Email delivery**: requires a provider account, verified domain and delivery
   credentials.
4. **Payments**: requires Stripe or GoCardless business verification, live keys
   and webhook configuration.
5. **Bank feeds**: requires a bank-feed provider agreement, credentials and
   client consent flow.
6. **HMRC production filing**: requires HMRC production credentials and each
   filing client’s taxpayer/agent OAuth authority.
7. **First Companies House live filing**: the package gate is set, but each
   real filing still requires an authorised operator, that client’s company
   authentication code, valid accounts and an explicit release of the send
   lock. New live packages can receive additional business-rule rejections, so
   the first filing must be controlled and reviewed.
8. **Pilot UAT execution**: the plan is ready; it requires named pilot users
   and their approval to use representative data.
