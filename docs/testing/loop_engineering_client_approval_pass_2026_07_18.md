# LedgerHouse Loop Engineering - Client Approval Pass

Date: 18 July 2026

## Objective

Continue the local-only LedgerHouse build loop by closing the next practical product gap: client approvals beyond VAT.

The app already had practice-side local accounts-department records, reports, PDF pack and ZIP export. The missing local capability was a general client approval queue where clients can review and approve/reject local management packs or statutory draft work before anything is finalised or filed externally.

## Built Locally

### Client Approval Records

Added `ClientApprovalRecord` with:

- Approval type: management pack, statutory accounts, tax review or other.
- Reference.
- Title and plain-English summary.
- Pending/approved/rejected status.
- Requested by/date.
- Decided by/date.
- Decision note.

### Local Suite Integration

The local accounts-department builder now creates:

- Management pack approval item.
- Statutory accounts draft approval item.

The accounts-department snapshot now counts:

- Total approval items.
- Pending approval items.

### Client Portal

The client portal now includes a general approval queue:

- Clients can see management pack approval items.
- Clients can see statutory accounts draft approval items.
- Clients can approve an item.
- Clients can reject an item.
- Clients can add an optional decision note.
- VAT review remains linked separately for VAT-specific approvals.

### Audit Trail

Client approval decisions create an `AuditEvent` with:

- Event type: `ClientApproval`.
- User.
- Approval item ID.
- Approval type.

### PDF And ZIP Outputs

The accounts-department PDF pack now includes client approval status.

The client ZIP data export now includes:

- `client_approval_records.csv`

## Files Changed

- `accounting/models.py`
- `accounting/operations.py`
- `accounting/reports.py`
- `accounting/views.py`
- `templates/accounting/client_portal.html`
- `static/accounting/dashboard.css`
- `accounting/tests/test_accounts_department_suite.py`
- `accounting/tests/test_client_portal_workflows.py`
- `accounting/migrations/0021_clientapprovalrecord.py`

## Test And Correction Log

### Migration

Command:

```text
docker compose exec -T web python manage.py makemigrations accounting
```

Result:

```text
Created accounting/migrations/0021_clientapprovalrecord.py
```

Command:

```text
docker compose exec -T web python manage.py migrate
```

Result:

```text
Applying accounting.0021_clientapprovalrecord... OK
```

### Focused Tests

Command:

```text
docker compose exec -T web python manage.py test accounting.tests.test_accounts_department_suite accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_can_review_local_approval_queue accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_management_reports_generate_csv_and_pdf
```

Result:

```text
Found 9 test(s).
Ran 9 tests in 7.679s
OK
```

### System Checks

Command:

```text
docker compose exec -T web python manage.py check
```

Result:

```text
System check identified no issues (0 silenced).
```

Command:

```text
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

```text
No changes detected
```

### Full Regression

First full regression pass found one failure:

- Existing test expected the old VAT-only approval wording.
- The app now correctly uses broader approval wording covering both VAT and local approval queue items.
- Test expectation was updated to assert the new client approval centre wording.

Focused correction test:

```text
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_portal_surfaces_plain_english_action_cards accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_client_can_review_local_approval_queue
```

Result:

```text
Found 2 test(s).
Ran 2 tests in 3.469s
OK
```

Second full regression pass:

```text
docker compose exec -T web python manage.py test --noinput
```

Result:

```text
Found 117 test(s).
Ran 117 tests in 109.424s
OK
```

The six-tenant end-to-end verification also completed:

```text
E2E verification of all 6 stages across 6 tenants successfully completed!
```

## Browser Verification

Browser test used the rendered local app.

Actions:

- Logged in as `admin`.
- Built/refreshed the local accounts-department suite.
- Opened client portal approval queue.
- Confirmed visible approval text:
  - `YOUR APPROVAL QUEUE`
  - `MANAGEMENT PACK TO`
  - `STATUTORY ACCOUNTS DRAFT TO`
  - `VAT AND TAX APPROVALS`
- Approved a pending item.
- Confirmed the decision note persisted.
- Downloaded the accounts-department PDF.
- Downloaded the client ZIP data export.

Browser result:

```text
errors: []
```

Downloaded PDF:

```text
CareCo Limited-accounts-department-pack.pdf
Header: %PDF
Size: 9,230 bytes
```

Downloaded ZIP:

```text
CareCo Limited-data-export.zip
Signature: PK
Size: 10,596 bytes
```

## Completed Locally

- Generic client approval queue.
- Management pack approval items.
- Statutory draft approval items.
- Client approve/reject actions.
- Client decision notes.
- Approval audit trail.
- Approval records in PDF pack.
- Approval records in ZIP data export.
- Focused tests.
- Corrected regression expectation.
- Full regression retest.
- Browser approval and download checks.

## Externally Blocked

Still not claimed as complete because these need external access or live setup:

- HMRC production filing.
- Companies House live filing.
- Live bank feeds.
- Live payment provider collection.
- Live email delivery.
- Public deployment, DNS and HTTPS.
- External legal/commercial review.

## Conclusion

This loop pass closed a genuine local SaaS workflow gap. Clients can now review and approve local practice work from the portal, and those decisions are recorded, audited, exported and included in the accounts-department pack.
