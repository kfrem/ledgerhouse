# Local 1-8 Development Completion Pass

Date: 2026-07-16

## Completed Locally

1. Client onboarding:
   - Client invitations now have an accept-invitation route.
   - Accepting an invitation creates or updates the user account.
   - Accepted users are linked to the correct tenant through `TenantUserAccess`.

2. Document intelligence:
   - Evidence can be analysed locally to suggest type, date, supplier/customer, amount, VAT and account code.
   - This is deterministic local extraction, not OCR. OCR can be plugged in later.

3. Evidence-to-bookkeeping:
   - Evidence with gross amount can now create a review journal using sales/purchase style postings.
   - The journal remains `RequiresReview` so the accountant approves it before final posting.

4. Reporting:
   - Management report context now includes aged debtors and aged creditors.
   - The report page exposes trading balances alongside profit, cash and net assets.

5. Billing abstraction:
   - Subscriptions now track provider, collection method, provider IDs, invoice status, next invoice date and last payment time.
   - The practice file can mark invoices issued and record manual payment locally.
   - Stripe/GoCardless API calls are intentionally not live until provider keys and webhook secrets are supplied.

6. HMRC and Companies House:
   - Existing local HMRC and Companies House screens remain intact.
   - Production filing remains external-authority gated.

7. Legal/commercial:
   - Existing terms/privacy routes remain available.
   - Final legal review remains a business/legal action before paid public launch.

8. Deployment:
   - Work remains local to avoid server cost.
   - Public DNS/HTTPS verification is deferred until the server is intentionally re-enabled.

## External Gates That Cannot Be Completed By Code Alone

- HMRC production approval and live client authorisation.
- Companies House filing/submission access beyond public company-data lookup.
- Stripe/GoCardless live API keys, webhook secrets and business verification.
- Final legal sign-off.
- Public production deployment and DNS/HTTPS verification.
