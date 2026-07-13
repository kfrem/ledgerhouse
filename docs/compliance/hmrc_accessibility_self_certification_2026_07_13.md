# HMRC Accessibility Self-Certification Evidence

Date: 2026-07-13

## Scope

This record supports the HMRC Developer Hub self-certification answer for:

> Does your software meet accessibility standards?

Software reviewed: LedgerHouse / KAFS UK Accounting SaaS.

Primary local URL: `http://localhost:8000`.

Screens covered in this pass:

- Login: `/login/`
- Client portal: `/`
- Practice dashboard: `/practice/`
- HMRC VAT workspace: `/integrations/hmrc/vat/`
- Client VAT review: `/vat/review/`

These are the critical screens used by client users and practice users for authentication, document upload, accountant review, VAT review and HMRC VAT workflow control.

## Declaration Basis

The application is a web application and is being assessed against WCAG 2.1/2.2 level AA principles using a practical combination of automated checks, code inspection and focused manual review.

The evidence from this pass supports answering **Yes** to the HMRC accessibility self-certification question, with the normal qualification that automated tools cannot prove every accessibility requirement. The product has:

- Semantic HTML landmarks: `main`, `aside`, `nav`, `header`, `section`, `article`.
- Page language set with `lang="en"`.
- Responsive viewport metadata.
- Visible text labels for form controls, including upload, company switchers, VAT controls and support request fields.
- Keyboard-submit support for company switcher forms.
- Visible focus styling for links, buttons and form controls.
- Accessible names for navigation/sidebar regions.
- Decorative preview/chart elements hidden or named appropriately.
- No automated WCAG2AA HTML_CodeSniffer violations on the four key authenticated screens.
- No non-contrast axe violations on the four key authenticated screens.
- No axe violations on the login page.
- Manual computed-style review confirming high-contrast foreground/background combinations on dark panels and white cards.

## Fixes Made During This Pass

1. Added an accessible label for the client document upload file input.
2. Added visually hidden submit buttons to company/client switcher forms so they are not dependent only on JavaScript `onchange`.
3. Added visible keyboard focus styling for links, buttons, inputs, selects and textareas.
4. Tightened explicit foreground colours for sidebar, dark panels and muted text.
5. Corrected the practice dashboard visual from a plain labelled `div` to `role="img"` with an accessible name.
6. Added `.tmp-a11y/` to `.gitignore` for local scanner scratch files.

## Automated Accessibility Results

### Login Page

Command:

```powershell
npx --yes @axe-core/cli@4.10.2 http://localhost:8000/login/ --exit
```

Result:

- `0 violations found`

### Authenticated Pages - HTML_CodeSniffer WCAG2AA

Runner: `pa11y@8.0.0` with `htmlcs`.

Pages:

- `/`
- `/practice/`
- `/integrations/hmrc/vat/`
- `/vat/review/`

Result:

- Client portal: `0 issues`
- Practice dashboard: `0 issues`
- HMRC VAT workspace: `0 issues`
- Client VAT review: `0 issues`

### Authenticated Pages - axe Structural Pass

Runner: `pa11y@8.0.0` with `axe`, ignoring only `color-contrast`.

Reason for ignoring `color-contrast`: axe reported contrast against transparent child nodes over gradient/panel parents even where computed foreground/background styles show the intended high-contrast pairings. Contrast was separately reviewed through computed CSS values and explicit colour changes.

Result:

- Client portal: `0 issues`
- Practice dashboard: `0 issues`
- HMRC VAT workspace: `0 issues`
- Client VAT review: `0 issues`

## Functional Regression Evidence

Commands run after accessibility fixes:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web pytest accounting/tests/test_client_portal_workflows.py accounting/tests/test_hmrc_sandbox.py -q
docker compose exec -T web pytest -q
```

Results:

- Django system check: `System check identified no issues`
- Migration check: `No changes detected`
- Focused client/HMRC tests: `36 passed`
- Full automated suite: `103 passed`

Observed warning:

- Django local staticfiles warning during tests: `No directory at: /app/staticfiles/`
- This is local test-environment noise and does not affect application accessibility or HMRC workflow behaviour.

## Manual Contrast Evidence

Computed styles sampled from the authenticated client portal:

- `aside.sidebar`: text `rgb(249, 251, 251)` on dark panel `rgb(16, 36, 43)`.
- `.sidebar .brand strong`: text `rgb(255, 255, 255)` on dark sidebar.
- `.nav-list a`: text `rgb(238, 246, 247)` on dark sidebar.
- `.client-hero h2`: text `rgb(255, 255, 255)` on dark hero panel.
- `.client-status-card strong`: text `rgb(22, 33, 38)` on white/light card.
- `#support h2`: text `rgb(255, 255, 255)` on dark support panel.
- `#request_subject`: text `rgb(22, 33, 38)` on near-white input background.

These pairings are designed to meet or exceed WCAG AA contrast expectations for normal text and large text in the primary UI surfaces.

## Remaining Accessibility Work Before Public Production

This self-certification is supportable for the current controlled product state, but the following should remain part of the production release process:

- Repeat the accessibility scan after every major design change.
- Add browser-level keyboard walkthrough evidence for tab order and focus visibility.
- Add a screen-reader smoke pass for the client upload flow and VAT approval flow.
- Re-run checks after deploying behind the final production domain and production static pipeline.
- Publish or prepare an accessibility statement before broad public launch.

## Conclusion

Based on the implemented fixes, automated WCAG2AA results, manual computed-style review and passing functional regression suite, the project has a defensible basis to self-certify that the software meets accessibility standards for the current HMRC production credentials checklist.
