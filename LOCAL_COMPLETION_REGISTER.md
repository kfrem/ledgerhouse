# LedgerHouse Local Completion Register

Date: 2026-07-12

This register separates what has been completed and verified locally from what cannot be completed without a live external service, public server, or third-party sandbox.

## Local Environment

- [x] Local Docker stack is running.
  - Evidence: `docker compose ps`
  - Services: `ledgerhouse_db` PostgreSQL 16, `ledgerhouse_web` Django at `http://localhost:8000/`
- [x] Local login is available.
  - URL: `http://localhost:8000/`
  - Username: `admin`
  - Password: `admin2`
- [x] Hetzner server is not required for the items in this register.
  - Current work is local-only to avoid ongoing server cost.

## Completed Locally

- [x] App design and screens.
  - Client portal exists at `/`.
  - Practice dashboard exists at `/practice/`.
  - Custom login screen exists at `/login/`.
  - Shared design system exists in `static/accounting/dashboard.css`.

- [x] Login flows.
  - Anonymous users are redirected to `/login/`.
  - Trial login `admin` / `admin2` works.
  - Authenticated users can access the client portal and practice dashboard.
  - Evidence: `accounting/tests/test_client_portal_workflows.py`.

- [x] Client portal logic.
  - Client can view plain-English finance status.
  - Client can upload files.
  - Client can see recently uploaded evidence.
  - Client can download CSV/PDF management reports.
  - Client portal does not expose admin accounting links.
  - Evidence: focused workflow tests pass.

- [x] Accountant/practice workflows.
  - Practice dashboard is separate from the client portal.
  - Practice workbench shows client upload inbox.
  - Practice workbench shows unmatched bank lines.
  - Practice workbench shows journals requiring review.
  - Practice dashboard links through to admin data records for accountant review.
  - Evidence: `test_practice_dashboard_surfaces_client_work_queues`.

- [x] File uploads.
  - CSV uploads are accepted.
  - XLSX uploads are accepted.
  - PDF/evidence uploads are accepted.
  - Other evidence-style files are stored in the evidence vault.
  - Evidence: `accounting/intake.py`, `accounting/tests/test_client_portal_workflows.py`.

- [x] Database logic.
  - PostgreSQL is used locally through Docker.
  - Double-entry journal balance constraints are tested.
  - Closed-period and VAT-lock protections are tested.
  - Audit immutability is tested.
  - Tenant isolation/RLS behaviour is tested on PostgreSQL.
  - Evidence: full pytest suite.

- [x] Docker build.
  - Local web image rebuild completed successfully.
  - Evidence: `docker compose build web`.

- [x] PostgreSQL migrations.
  - No missing migrations.
  - Evidence: `docker compose exec -T web python manage.py makemigrations --check --dry-run`.

- [x] Accounting calculations.
  - Trial balance checks are covered.
  - VAT calculations are covered.
  - Bank reconciliation calculations are covered.
  - Payroll and CIS journal calculations are covered.
  - Evidence: full pytest suite.

- [x] Reports.
  - CSV management report generation works.
  - PDF management report generation works.
  - Trial balance export logic is tested.
  - VAT report logic is tested.
  - Evidence: `accounting/reports.py`, `accounting/tests/test_client_portal_workflows.py`, full pytest suite.

- [x] CSV/XLSX/PDF processing.
  - CSV bank statement import tested.
  - XLSX bank statement import tested through `openpyxl`.
  - PDF/evidence storage tested.
  - Demo files regenerated for all seeded clients.
  - Evidence: `docker compose exec -T web python manage.py build_demo_files`.

- [x] Seeded realistic demo data.
  - CareCo Limited.
  - CharityCo Foundation.
  - ConsultCo Consulting.
  - LogisticsCo Transport Ltd.
  - TechCo Software Ltd.
  - TradeCo Retail.
  - Evidence: `docker compose exec -T web python manage.py seed_db`.

- [x] Most automated tests.
  - Focused client/practice workflow tests: `8 passed`.
  - Full suite: `69 passed`.
  - Only warning observed: Django local staticfiles directory warning during tests; it does not fail the suite.

## Verified Commands From This Pass

- [x] `docker compose ps`
- [x] `docker compose exec -T web python manage.py check`
- [x] `docker compose exec -T web python manage.py makemigrations --check --dry-run`
- [x] `docker compose exec -T web python manage.py seed_db`
- [x] `docker compose exec -T web python manage.py build_demo_files`
- [x] `docker compose exec -T web pytest accounting/tests/test_client_portal_workflows.py -q`
- [x] `docker compose exec -T web pytest -q`
- [x] `docker compose build web`

## Not Completed Locally Because Of Specific Constraints

- [ ] Public subdomain test for `ledgerhouse.finaccord.pro`.
  - Constraint: requires a live public server or tunnel target for DNS to resolve to.
  - Local substitute completed: app is accessible at `http://localhost:8000/`.

- [ ] Real HTTPS certificate issuance.
  - Constraint: requires public DNS pointing at a reachable server so Caddy/Let's Encrypt can validate the domain.
  - Local substitute completed: production Caddy configuration exists in Hetzner cloud-init and deployment files, but live issuance is external-only.

- [ ] Public user access from outside this machine.
  - Constraint: requires a public deployment, VPN, or tunnel.
  - Local substitute completed: authenticated local browser and Django tests verify the app flows.

- [ ] Real email delivery.
  - Constraint: requires an email provider account, verified sending domain, credentials, and DNS records.
  - Local substitute completed: no production email sending has been enabled, so there is no accidental billing or live sending.

- [ ] Real Open Banking connection.
  - Constraint: requires a real provider account, OAuth/callback URLs, consent flow, and bank sandbox/live credentials.
  - Local substitute completed: mock Open Banking connection and sync logic are tested.

- [ ] Real HMRC MTD VAT filing.
  - Constraint: requires HMRC developer/app credentials, callback URL, organisation authorisation, and sandbox/live filing setup.
  - Local substitute completed: mock HMRC VAT payload/filing flow is tested.

- [ ] Payment provider callbacks.
  - Constraint: requires a chosen payment provider, account credentials, public webhook URL, and signed webhook testing.
  - Local substitute completed: payment provider integration is not currently part of the implemented local product.

- [ ] Production load/performance under real users.
  - Constraint: requires a deployed environment or a dedicated local load-test target and agreed user-volume target.
  - Local substitute completed: functional tests pass, but load testing has not been scoped yet.

- [ ] Production backup restore drill.
  - Constraint: proper proof requires the final production database/storage location and backup policy.
  - Local substitute completed: local database dump backup exists from the deleted server, and local Docker PostgreSQL is running.

## Next Constraint To Deal With First

Recommended next constraint: decide whether the next external proof should be a free/local tunnel demo or a short paid server redeploy.

- Free/local tunnel path: useful for a temporary client-style preview, but not ideal for production reliability.
- Paid server redeploy path: useful only when the app is ready for an external tester or client.
