# LedgerHouse Local 1-8 Execution Report

Date: 2026-07-16

## Scope

This pass continued local development for the eight requested areas without using the external server or charging/payment-provider APIs.

## Completed

### 1. Real Client Onboarding

- Added invitation acceptance route: `/invite/<invitation-id>/`.
- Accepting an invitation creates or updates a Django user.
- Accepted users are linked to the invited company using `TenantUserAccess`.
- Invitations now record `accepted_by`.
- Practice client file displays the accept link while the invitation is pending.

### 2. Document Intelligence

- Added local evidence analysis that can infer:
  - document type
  - supplier/customer
  - date
  - gross amount
  - VAT amount
  - suggested account code
- Added `Analyse` action from the evidence queue and evidence detail page.
- This is local deterministic parsing, not OCR. OCR remains a later enhancement.

### 3. Evidence-To-Bookkeeping

- Evidence with captured amounts can now create a review journal.
- Purchase-style evidence posts:
  - debit expense
  - debit VAT where present
  - credit aged creditors
- Sales-style evidence posts:
  - debit aged debtors
  - credit revenue
  - credit VAT where present
- Created journals stay `RequiresReview` so the accountant approves before final posting.

### 4. Reports

- Added aged debtors and aged creditors to report context.
- Added those figures to:
  - CSV report
  - standard PDF report
  - management pack PDF
  - in-app management report page

### 5. HMRC Readiness

- Existing HMRC local/sandbox workflow remains intact.
- No live HMRC filing was attempted.
- Production access remains dependent on HMRC approval and real client authorisation.

### 6. Companies House Readiness

- Existing Companies House public-data workflow remains intact.
- Submission/filing access remains an external Companies House process.

### 7. Legal/Customer Documentation

- Existing terms/privacy routes remain intact.
- Added this report and a development note documenting local versus external gates.

### 8. Payment/Billing

- Extended subscriptions with:
  - billing provider
  - collection method
  - provider customer ID
  - provider subscription ID
  - latest invoice status
  - next invoice date
  - last payment time
- Practice users can:
  - save provider/collection details
  - mark invoice issued
  - record manual payment
- This prepares Stripe/GoCardless integration without requiring live API keys yet.

## Tests Run

```text
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows
docker compose exec -T web python manage.py test
```

## Results

```text
System check: passed
Migration check: no changes detected
Focused workflow suite: 26 tests OK
Full project suite: 108 tests OK
Browser smoke: passed
```

Browser smoke confirmed:

- Practice client file shows invite flow.
- Practice client file shows billing provider controls.
- Practice client file shows record payment action.
- Evidence queue shows analyse/post actions.
- Management report shows aged debtors and aged creditors.

## Remaining External Gates

These are not coding blockers. They require external approval, credentials or business decisions:

- HMRC production approval and live client authorisation.
- Companies House filing/submission access beyond public lookup APIs.
- Stripe or GoCardless live API keys, webhook secrets and business verification.
- Final legal review of customer-facing terms/privacy/DPA.
- Public deployment, DNS and HTTPS verification.
