# LedgerHouse Live Online Synthetic Accounting Workflow

Date: 2026-08-09

## Scope

This was a live deployment verification using a clearly labelled synthetic
company and synthetic accounting records. No client records, bank credentials,
HMRC requests, Companies House submissions, payment transactions or emails
were sent.

## Production corrections made

- Enabled `accounting.middleware.TenantMiddleware` after Django authentication.
- Updated tenant selection to use only the authenticated user's authorised
  company memberships, with a permitted `company` query parameter where set.
- Hardened Companies House credential-file loading: an unreadable local secret
  now resolves to an unavailable integration state instead of causing a portal
  error.
- Granted the restricted PostgreSQL tenant role access to the current schema
  tables and sequences. PostgreSQL RLS remains enabled and was not bypassed.
- Corrected the mounted Companies House credential file ownership so that the
  non-root LedgerHouse process can read its own mounted file. No secret value
  was read or recorded.

## Synthetic records created

Company: `LedgerHouse Online Test Company (Synthetic)`.

- Six balanced source journals: opening balance, sale, customer receipt,
  supplier invoice, supplier payment and bank charge.
- One evidence-review journal generated from the uploaded synthetic purchase
  invoice.
- One synthetic supplier-invoice text file in the evidence vault.
- One synthetic bank CSV containing four bank lines.

All records are expressly marked as online test data and are not filing data.

## Browser checks

| Route | Result |
| --- | --- |
| `https://ledgerhouse1.finaccord.pro/` | Client portal loaded for the synthetic company after the tenant/RLS correction. |
| Client upload workflow | Bank CSV imported four lines; evidence document stored and classified as `PurchaseInvoice`. |
| Client portal summary | Counts and profit figures updated from saved records. |
| Management report | Rendered revenue, costs, profit, cash, evidence and bank-workflow counts from the same live tenant records. |
| `/practice/evidence/` | Evidence queue showed the uploaded document, review data and linked evidence journal. |
| `/practice/banking/` | Banking queue showed the four imported unmatched transactions. |
| Duplicate bank upload | Re-upload returned the explicit idempotency message and did not create extra bank lines. |

## Command checks

| Check | Result |
| --- | --- |
| Production Docker rebuild and health endpoint | Passed. |
| External `healthz` request | Passed with `status: ok`. |
| Tenant-scoped integrity query | 7 journals, 14 lines, 4 bank lines, 1 evidence document, 1 imported file, 0 unbalanced journals. |

## Result and limits

The live client intake, evidence review, accounting journal, banking queue and
management-report paths passed with synthetic online data. This does not prove
live HMRC or Companies House filing, real bank connectivity, customer payment
collection or use with real client documents. Those provider and commercial
workflows require their own controlled tests and approvals.
