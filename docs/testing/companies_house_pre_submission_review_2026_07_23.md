# LedgerHouse Companies House Accounts Pre-submission Review

Date: 23 July 2026

## Scope and decision

This review covers local preparation for Companies House XML Gateway accounts
testing. It does not claim Companies House approval and no test submission was
sent during this pass. Local submission records at the end of the pass were:
zero created and zero submitted.

The work responds to the reviewer requirement that accounts must render as a
report, rather than a continuous stream of labels and facts. The generated
documents use a cover page, separately paginated financial statements, HTML
tables, left-aligned descriptions, right-aligned GBP amounts, totals, bracketed
negative values, statutory statements, approval information and embedded CSS.

## Inputs reviewed

- `Statement_of_Requirements_CH_Accounts_Filing.docx`
- `GSEL R TECH LIMITED_FullAccounts_2025 (1).pdf`
- `GSEL R TECH LIMITED_Accounts_2025.html`
- `UK_Chart_of_Accounts_Master_v2.xlsx`
- Companies House liaison email from Mr Ioan explaining visual review,
  supported filing types and product-specific test credentials/package references.

## Implemented local controls

1. Report-style XHTML/iXBRL generation for micro-entity, small unaudited,
   filleted, dormant and amended accounts profiles.
2. Explicit comparative facts only. A second-year column and prior-period
   contexts are emitted only when complete comparative figures have been
   recorded; figures are never invented.
3. Filing drafts now require an approval date and approving director name.
   Placeholder approval text causes local validation to fail.
4. Monetary facts use GBP, decimal and scale attributes, readable comma
   formatting and bracketed negative values with the matching iXBRL sign.
5. Micro-entity accounts use the FRS 102 entry point with the required
   `Micro-entities` accounting-standard dimension. Small accounts use FRS 102.
   This follows the TIS guidance for FRS 105 micro-entity filing.
6. Submission numbers are allocated atomically and incrementally per registered
   software product, preventing cross-product credential/package-reference use.
7. The workspace sends no XML Gateway traffic unless an operator deliberately
   enables `COMPANIES_HOUSE_FILING_SEND_ENABLED`; the normal local state is
   locked. The interface shows that lock.
8. Staff can retrieve an inline XHTML/iXBRL preview before sending a package.
9. An evidence ZIP records sanitized Gateway XML, generated iXBRL samples,
   scenario results, approval controls and non-secret status information.

## Local scenarios exercised

All eight scenarios passed local iXBRL validation, filing-readiness checks and
Gateway wrapper construction:

- micro profit
- small unaudited
- dormant
- amended accounts
- two-year comparative accounts
- loss-making accounts
- asset-led accounts
- creditor-heavy accounts

The fresh evidence pack is:

`output/companies_house/review/ledgerhouse_ch_pre_submission_evidence_2026_07_23_v12.zip`

It contains the rendered XHTML/iXBRL source files under `ixbrl/` and sanitized
Gateway documents under `gateway_xml/` for review before any external send.

## Official Companies House validator evidence

The final v12 evidence-pack XHTML files were individually uploaded to the
Companies House **test iXBRL validator**. This is a validation-only service;
it is not the XML Gateway and generated no submission number or filing.

| Scenario | Official validator result |
| --- | --- |
| `micro-profit.xhtml` | valid |
| `small-unaudited.xhtml` | valid |
| `dormant.xhtml` | valid |
| `amended.xhtml` | valid |
| `comparative.xhtml` | valid |
| `loss-making.xhtml` | valid |
| `fixed-assets.xhtml` | valid |
| `creditor-heavy.xhtml` | valid |

The service confirmed for every file that it met the iXBRL specification and
Companies House business validation rules. Its rendered-image preview was
available for each successful result.

Earlier validator findings were used as defect reports and corrected before
the successful v12 run: XHTML schema layout, context period types, default
dimensions, mandatory balance-sheet date, average employee count, and the
micro-entities / dormant statutory statements.

## Tests and checks run

| Command | Result |
| --- | --- |
| `docker compose exec -T web python manage.py test accounting.tests.test_ixbrl_report_presentation accounting.tests.test_companies_house.CompaniesHouseFilingTests --verbosity 1 --noinput` | 34 passed |
| `docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows.ClientPortalWorkflowTests.test_pdf_upload_stores_evidence_document accounting.tests.test_ixbrl_report_presentation accounting.tests.test_companies_house.CompaniesHouseFilingTests --verbosity 1 --noinput` | 35 passed |
| `docker compose exec -T web python manage.py build_companies_house_scenarios --strict` | 8 of 8 scenarios passed |
| `docker compose exec -T web python manage.py check --database default` | passed, no issues |
| `docker compose exec -T web python manage.py makemigrations --check --dry-run` | passed, no changes detected |
| `docker compose exec -T web python manage.py test --verbosity 1 --noinput` | 179 passed in 179.731 seconds after the final Companies House corrections |
| `docker compose ps` | PostgreSQL healthy; Django web service running on port 8000 |
| `docker compose exec -T web python manage.py test accounting.tests.test_ixbrl_report_presentation accounting.tests.test_companies_house --verbosity 1 --noinput` | 43 passed after the final validator-led corrections |
| `docker compose exec -T web python manage.py build_companies_house_scenarios --strict` | 8 of 8 scenarios passed after the final corrections |
| `docker compose exec -T web python manage.py check --database default` | passed, no issues after the final corrections |
| `docker compose exec -T web python manage.py makemigrations --check --dry-run` | passed, no changes detected after migration `0026` |

One cross-module regression was found during the first full run: evidence intake
had lost the exact practice-review outcome text expected by the client upload
workflow. It was corrected in `accounting/intake.py`, tested directly, then the
complete suite was rerun successfully.

## Visual-review evidence

The report uses statement tables, left-aligned labels and right-aligned GBP
figures. The Companies House validator made a publication-image preview
available for every successful v12 file. This is the correct external image
check for the accounts that would be displayed on the register.

## Companies House XML Gateway test submissions - 23 July 2026

After the final local and official-validator checks, LedgerHouse transmitted one
controlled XML Gateway **test** submission for each accounts filing profile in
its initial support scope. The production safety lock remained enabled outside
the one-off test process, and every Gateway envelope carried test flag `1`.

| Filing profile | Gateway submission number | Initial Gateway response | Status after status poll |
| --- | --- | --- | --- |
| Micro entity | `000001` | submitted | pending |
| Small unaudited | `000002` | submitted | pending |
| Dormant | `000003` | submitted | pending |
| Amended micro entity | `000004` | submitted | pending |

The numbers were allocated by LedgerHouse's database-backed sequence in order,
with no pre-existing submission records. The Gateway did not return a transport
or rejection error for any of the four transmissions. A first status poll was
recorded for each submission; all remain `Pending`, which is an asynchronous
processing status and is **not** an acceptance result. The next evidence update
must record the final accepted or rejected state returned by Companies House.

The post-transmission evidence archive is:

`output/companies_house/review/ledgerhouse_ch_gateway_test_2026_07_23.zip`

The protected credential file was made available to the local Docker container
only for this controlled transmission and was removed from that container after
the first status polls. It was not added to the repository or evidence archive.

## Still external and deliberately not claimed

1. Obtain the final Gateway outcomes for submissions `000001` to `000004` and
   investigate any rejection before sending a replacement with the next number.
2. Obtain the consistent accepted Gateway submission numbers Mr Ioan requested for each
   type LedgerHouse will support, then send those numbers to him for review.
3. Obtain accountant/legal review of statutory wording, filing scope and client
   engagement responsibilities before public use.
4. Keep live filing disabled until Companies House issues the appropriate
   approval and distinct live settings are deliberately configured.

## Recommended review sequence

1. Agree the initial supported types: micro, small unaudited, dormant and
   amended if each will be offered at launch. The supporting financial-shape
   scenarios in the same package have also passed independent validation.
2. Continue polling the four test submissions until Companies House returns a
   terminal status, retaining every acknowledgement and poll result.
3. If all four are accepted, send Mr Ioan the submission numbers for review.
   If a submission is rejected, correct the specific error and use the next
   unused number for the replacement.
