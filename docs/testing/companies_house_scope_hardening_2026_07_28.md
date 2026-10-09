# LedgerHouse Companies House Scope Hardening - 28 July 2026

## Objective

Close the remaining local Companies House readiness gap identified while the
XML Team reviews the initial test submission set. The work deliberately does
not submit a new Gateway filing or enable production filing.

## Completed

1. Added **Small unaudited filleted accounts** as a formal local scenario:
   `SmallUnauditedFilleted`.
2. Declared the initial LedgerHouse accounts-filing scope in code and the
   Companies House workspace:
   - Micro-entity accounts
   - Small unaudited full accounts
   - Small unaudited filleted accounts
   - Dormant company accounts
   - Amended micro-entity accounts
3. Added a filing-scope gate. Attempts to build a gateway document for an
   unsupported filing type raise a clear error before a submission number can
   be allocated.
4. Preserved comparative micro-entity accounts as a permitted data/presentation
   variant rather than incorrectly treating them as a separate filing type.
5. Added the unsent second-round test-plan command. It records the existing
   first-round references and does not allocate a number or contact Companies
   House.
6. Polled the existing XML Gateway tests. Each remains `Pending` with no
   rejection message:
   - `000001` micro entity
   - `000002` small unaudited full
   - `000003` dormant
   - `000004` amended micro entity
7. Improved the mobile Companies House workspace navigation. It now uses a
   compact two-column phone layout and brings the workspace into the first
   viewport.

## Second-round Position

The prepared plan is:

`docs/testing/companies_house_second_round_test_plan_2026_07_28.md`

The filleted accounts profile requires its initial Gateway test before a second
round can be completed. The second Gateway round is intentionally unsent while
the XML Team confirms the declared scope and whether amended accounts should be
counted as a separate filing type. No submission number has been reserved for
that plan.

## Tests and Evidence

| Check | Result |
| --- | --- |
| Focused Companies House/iXBRL tests | 44 passed |
| Local scenario builder | 9 of 9 passed |
| Full Django test suite | 186 passed in 63.169 seconds |
| Local acceptance suite | passed: client, practice, reports, PDF, ZIP and handover checks |
| Migration check | passed, no changes detected |
| Django system check | passed, no issues |
| Browser check, desktop | practice dashboard rendered with no horizontal overflow |
| Browser check, mobile 390 x 844 | Companies House scope, scenario and test-status views rendered cleanly after compact navigation adjustment |
| Docker | PostgreSQL healthy; web service running on port 8000 |

The regenerated sanitized evidence archive is:

`output/companies_house/review/ledgerhouse_ch_scope_hardening_2026_07_28.zip`

## Still External

1. Send the scope response to Mr Ioan and obtain his confirmation on whether
   amended accounts are a separate filing type for the requested further round.
2. Submit one initial filleted-accounts test and the requested additional round
   using the next consecutive numbers only after that confirmation.
3. Wait for Companies House test outcomes and formal authorisation before any
   production filing configuration is considered.
