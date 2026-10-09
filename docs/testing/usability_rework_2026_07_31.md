# LedgerHouse Usability Rework - 31 July 2026

## Purpose

This pass responds to user feedback that LedgerHouse was visually busy, had inconsistent type sizing, and did not make the first action clear to a client or accountant. The accounting model, permissions and workflows were not changed. The work changed the presentation of those existing workflows.

## Benchmarks reviewed

The following established accounting products informed the review. Their screens and published product material were used for patterns, not copied designs.

1. Capium Accounts Production: compact left navigation, dense register-style tables, a clear client context and direct actions for reports, iXBRL and submission status.
2. Xero dashboard: a permission-aware snapshot of bank accounts, invoices and bills, arranged as scanable widgets with configurable relevance.
3. QuickBooks dashboard: prominent next actions and concise views of cash flow, invoices, expenses and reports.
4. FreeAgent: simple small-business and practice summaries with a client-level profit-and-loss view.

## Findings in the previous LedgerHouse presentation

1. The practice landing page used a large decorative hero and simulated chart before work queues.
2. Headline sizes ranged up to 5.6rem across pages, which made ordinary operational screens feel like marketing pages.
3. Workflow counts appeared in multiple competing card layouts, making it unclear what needed action first.
4. The client page used technical phrases such as "finance hub", "bookkeeping entries" and "compliance estimate" in the first screen.
5. A first responsive check exposed a real mobile overflow caused by a desktop workspace margin being reapplied after the mobile breakpoint.

## Changes made

1. Replaced the practice decorative hero with a compact `Today` header and two clear next actions.
2. Added a scan-first `Work needing attention` queue using real existing workflow counts and links.
3. Reworded primary navigation and module descriptions to distinguish core accounts work from VAT/compliance.
4. Applied a shared compact operational UI layer in `static/accounting/dashboard.css`:
   - 15px body base and 1.7rem primary page headings.
   - 6px working-surface radii, restrained shadows and no new decorative gradients.
   - compact navigation, buttons, metrics, lists and register rows.
   - reduced page-specific hero and client-card typography.
5. Reworded the client landing page around a client task: send records, review requests and approve work. It now calls the accounting status `Company summary` and tax work `Tax and filings`.
6. Corrected the responsive rule so the sidebar becomes static and the workspace margin becomes zero at widths at or below 820px.
7. Updated workflow tests to assert the revised product language, and added a static UI contract test for the compact shared CSS selectors.

## Verification

### Automated

Run after the final change:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_static_assets accounting.tests.test_client_portal_workflows accounting.tests.test_accounts_production --noinput
docker compose exec -T web python manage.py check
git diff --check
```

Focused result: 37 tests passed. Django system check: no issues. `git diff --check`: no whitespace errors; Git reported existing CRLF conversion notices only.

Full regression result: 194 tests passed in 67.224 seconds from a fresh Django test database.

Additional local acceptance result:

```powershell
docker compose exec -T web python manage.py local_acceptance_suite --strict --output docs/testing/local_acceptance_suite_2026_07_31_usability.md
docker compose exec -T web python manage.py commercial_readiness_rehearsal --strict --output docs/testing/commercial_readiness_rehearsal_2026_07_31_usability.md
```

Both commands passed. The acceptance suite verified 8 of 8 local accounts-department phases; client portal, practice dashboard, accounts department, accounts production and management report pages; CSV, PDF, pack and ZIP downloads; and the local handover ZIP. The commercial rehearsal passed for six seeded client types, including evidence-to-ledger, banking, balanced trial balances, reports, the production register and external filing safety.

### Browser checks

1. Practice overview loaded with compact navigation, a clear page title, a `Today` panel and a work priority queue.
2. Accounts department suite loaded with all data cards and work tables rendered.
3. Client portal at 390px showed no horizontal overflow after the responsive correction. Computed state: `scrollWidth <= innerWidth`, static sidebar, zero workspace margin.
4. Practice workspace at the available wide browser layout showed no horizontal overflow.
5. Browser console logs were empty for warning and error levels on the practice, accounts department and client pages.

## Limitations

This is a local usability verification with seeded data. It does not replace moderated tests with real client users, accessibility testing with a screen reader, or production deployment testing. The next useful check is to ask the two reviewers to repeat the same first-screen review after this build, using one client and one practice workflow.
