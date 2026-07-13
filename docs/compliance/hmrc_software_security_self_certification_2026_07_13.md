# HMRC Software Security Self-Certification Evidence

Date: 2026-07-13

Software: LedgerHouse / KAFS UK Accounting SaaS.

## Scope

This record supports the HMRC Developer Hub software-security checklist answers for the production credentials request.

## Security Controls Verified

- LedgerHouse is a SaaS application with authenticated client and practice workspaces.
- Practice, HMRC and Companies House workbenches are restricted to staff users.
- Non-staff client users can only access tenant records assigned through `TenantUserAccess`.
- CSRF protection is enabled for state-changing forms.
- CSRF cookies are HTTP-only.
- Stored HMRC OAuth access tokens, HMRC refresh tokens and bank consent tokens are encrypted at the application field level.
- Responses set security headers for CSP, Permissions-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Cross-Origin-Opener-Policy, Cross-Origin-Embedder-Policy and Cross-Origin-Resource-Policy.
- Inline styles/events were removed so the CSP no longer requires `unsafe-inline`.
- Docker/PostgreSQL runtime is used locally and is aligned with the deployment architecture.

## Penetration/Security Scan

OWASP ZAP baseline scan was run against the local application on 2026-07-13:

- Target: `http://host.docker.internal:8000`
- Result: `FAIL-NEW: 0`, `FAIL-INPROG: 0`, `PASS: 60`
- Evidence files:
  - `docs/compliance/hmrc_zap_baseline_2026_07_13.html`
  - `docs/compliance/hmrc_zap_baseline_2026_07_13.json`

Warnings remaining after mitigation:

- Static CSS served by Django local runserver did not include every production header. Production static serving is through WhiteNoise/Caddy/static pipeline rather than the local development handler.
- Local development `Server` header exposes the Django runserver/CPython version. Production must not run Django `runserver`; it should use the production WSGI/ASGI server behind Caddy.
- ZAP identified the login request and session management responses. These are expected authentication/session endpoints, not a failure.
- ZAP reported a potential controllable HTML attribute on the login `next` flow. This is Django's standard login redirect parameter and must remain constrained to same-host redirects.
- ZAP reported non-storable content observations on authenticated/login routes. These responses already include no-cache/no-store directives.

## Automated Test Evidence

- `accounting.tests.test_client_portal_workflows`: 20 tests OK after security header and access-control changes.
- Full suite after tenant-user access and data export changes: 100 tests OK.
- Django system check: no issues.
- Migration check: no changes detected.

## Production Conditions

The software-security self-certification assumes production is deployed with:

- `DEBUG=False`.
- A real `SECRET_KEY` outside source control.
- `FIELD_ENCRYPTION_KEY` set to a Fernet key outside source control.
- HTTPS/TLS enabled at the reverse proxy.
- Django served by a production application server, not `runserver`.
- Static files served through the production static pipeline.
- Restricted PostgreSQL application role from `deploy/create_app_role.sql`.

On that basis, the current controlled application has a defensible basis to answer **Yes** to the HMRC software penetration-testing question: a recognised penetration/security scan was run, produced zero failures, and remaining warnings are documented with mitigation or production-context explanation.
