# LedgerHouse Local Acceptance Suite

Generated: 2026-07-28T16:36:53.031262+00:00
Tenant checked: CareCo Limited

## Phase Coverage

8 of 8 local accounts department phases passed.

## Checks

- PASS Accounts department phases: 8 of 8 local phases passing.
- PASS Client portal: /?company=76168495-36f8-5eb6-9e25-fdce5c9213ef returned 200; expected marker 'Your accounts department'.
- PASS Practice dashboard: /practice/ returned 200; expected marker 'Portfolio command centre'.
- PASS Accounts department: /practice/accounts-department/?company=76168495-36f8-5eb6-9e25-fdce5c9213ef returned 200; expected marker 'Accounts department suite'.
- PASS Management report: /reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/ returned 200; expected marker 'What the figures mean'.
- PASS Management CSV: /reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/csv/ returned 200 with text/csv.
- PASS Management PDF: /reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/pdf/ returned 200 with application/pdf.
- PASS Management pack: /reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/pack/ returned 200 with application/pdf.
- PASS Accounts department pack: /reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/accounts-department-pack/ returned 200 with application/pdf.
- PASS Client data ZIP: /reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/zip/ returned 200 with application/zip.
- PASS No-HMRC handover ZIP: Generated ZIP with 15 tenant result(s).

## External Boundary

This acceptance suite deliberately avoids HMRC live filing, Companies House live filing, bank-feed access, payment provider actions, DNS changes and server deployment.

## Next Developer Instruction

Run `python manage.py local_acceptance_suite --strict` after local changes, then run the full Django regression suite before handover.
