# LedgerHouse Full Local Development Pass

Date: 2026-07-15
Environment: local Docker stack on Windows, Django app at `http://127.0.0.1:8000`, PostgreSQL container `ledgerhouse_db`.

## Purpose

This pass was carried out to complete as much of the LedgerHouse SaaS product as possible without relying on a paid external server, HMRC production access, Companies House submission-only services, or a live payment provider.

The focus was the eight outstanding development areas:

1. Core product polish and client-facing screens.
2. Accounting workflow depth.
3. Reports and client export pack.
4. HMRC readiness and local VAT workflow continuity.
5. Companies House readiness and local workflow continuity.
6. Deployment readiness while keeping work local.
7. Legal/customer documentation continuity.
8. Commercial SaaS onboarding and billing controls.

## Work Completed In This Pass

### 1. Core product polish and client-facing screens

- Kept the client portal route working after authentication.
- Added a management-pack export link into the client report actions.
- Verified the client portal in a real browser session after logging in with the local test user.

### 2. Accounting workflow depth

- Extended evidence documents with bookkeeping review metadata:
  - document category
  - supplier/customer name
  - document date
  - gross amount
  - VAT amount
  - suggested nominal account
  - review note
- Updated the practice evidence review form so staff can triage evidence without using Django admin.
- Added an evidence detail page with inline PDF/image preview support, linked journals and audit history.
- Added protected file-serving route for evidence previews/downloads.
- Preserved audit events when evidence review actions are taken.

### 3. Reports and client export pack

- Added a multi-page management accounts PDF pack covering:
  - executive summary
  - balance sheet style summary
  - profit and loss by month
  - VAT and filing summary
  - workflow status
- Added the management pack download route via `/reports/<tenant>/pack/`.
- Added the pack link to the client portal and management report page.
- Expanded the client data export ZIP to include:
  - richer evidence metadata in `evidence_documents.csv`
  - `client_invitations.csv`
  - `subscription.csv`

### 4. HMRC readiness

- Confirmed the existing HMRC/VAT local workspace and tests still pass.
- No new HMRC production API action was taken in this pass because production API behaviour depends on HMRC approval and live credentials.
- Local HMRC-related code remains covered by the full Django suite.

### 5. Companies House readiness

- Confirmed the existing Companies House workspace and tests remain part of the full passing suite.
- No new Companies House external request was required in this pass because REST API key flow and local integration scaffolding already exist.
- Any filing or submission route that requires a formal Companies House process remains an external approval constraint.

### 6. Deployment readiness

- Kept the work local and Docker-based to avoid further cloud cost.
- Applied the new database migration to the local PostgreSQL container.
- Verified there are no pending model changes after migration generation.
- Did not redeploy to the external server.

### 7. Legal/customer documentation continuity

- Existing public `/privacy/` and `/terms/` routes remain covered by tests.
- Existing compliance and customer documentation remains in `docs/compliance`, `docs/legal` and `docs/deployment`.
- This pass adds this report as a development and testing audit trail.

### 8. Commercial SaaS onboarding and billing controls

- Added `ClientInvitation` model for preparing tenant-specific client invitations.
- Added `SubscriptionPlan` model for tenant billing status, plan name, price, currency and billing notes.
- Added practice client-file controls to prepare invitations and update subscription/billing status.
- Added audit events for invitation and subscription changes.
- Added admin support for invitation and subscription records.

## Database Changes

Migration added:

- `accounting/migrations/0017_evidencedocument_document_category_and_more.py`

Objects added or extended:

- `EvidenceDocument`: new review/accounting metadata fields.
- `ClientInvitation`: tenant-specific invitation tracking.
- `SubscriptionPlan`: tenant-specific billing status tracking.

Migration result:

```text
docker compose exec -T web python manage.py migrate
Applying accounting.0017_evidencedocument_document_category_and_more... OK
```

## Automated Test Evidence

### Django system check

```text
docker compose exec -T web python manage.py check
System check identified no issues (0 silenced).
```

### Migration consistency

```text
docker compose exec -T web python manage.py makemigrations --check --dry-run
No changes detected
```

### Focused workflow tests

```text
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows
Ran 24 tests in 20.765s
OK
```

Covered in the focused tests:

- public privacy and terms pages
- client portal
- practice client file
- client invitation and subscription status
- client question status updates
- unmatched bank review and posting
- ledger review and approval
- evidence review, evidence detail, evidence file serving
- management CSV/PDF/ZIP/PDF pack exports
- local production readiness command

### Full project test suite

```text
docker compose exec -T web python manage.py test
Ran 106 tests in 39.643s
OK
```

The full suite also reported the existing local-development warning:

```text
accounting.W001 Database 'default' connects as a superuser or BYPASSRLS role.
```

This is expected in the local Docker development stack. Production should use the restricted application role already documented in `deploy/create_app_role.sql`.

## Browser Smoke Test Evidence

Browser automation used installed Chrome against `http://127.0.0.1:8000`.

Passed checks:

- Login with local test credentials.
- Client portal renders after login.
- Management report page opens from the client portal.
- Practice dashboard renders.
- Evidence review queue renders.
- Ledger review queue renders.
- Banking review queue renders.
- Session was cleared and the login page rendered again.

Result summary:

```text
ok: true
login: passed
client portal: passed
management report: passed
practice dashboard: passed
evidence review: passed
ledger review: passed
banking review: passed
logout/session clear: passed
```

## Important Constraints Still Outside Local Development

The following cannot be fully completed locally without external services or approvals:

- HMRC production API approval and live taxpayer authorisation.
- HMRC production filing against real client obligations.
- Companies House filing/submission workflows that require a formal Companies House route beyond the public REST API.
- Real payment collection, card handling, invoices and subscription charging through a payment provider.
- Final legal sign-off of the customer terms, privacy notice and data processing wording.
- Final production deployment and DNS/HTTPS verification on the public domain.

## Current Outcome

The local application now has stronger client-facing workflow, practice evidence review, audit trail, reporting pack, export pack and SaaS billing/onboarding scaffolding. The code was migrated, tested with focused workflow tests, tested with the full Django suite, and exercised in a browser session.

The remaining work is not blocked by local coding capability. It is blocked by external credentials, approvals, live service configuration or business/legal decisions.
