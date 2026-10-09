# Companies House Local Waiting Pass

Date: 2026-07-21

## Scope

Local-only build work completed while waiting for Companies House to confirm the required number and type of test submissions. No extra live/customer filing was performed in this pass.

## Built

- Added a repeatable Companies House local scenario engine in `accounting/companies_house_scenarios.py`.
- Added 8 locally built accounts scenarios:
  - micro-entity profit
  - small unaudited
  - dormant
  - amended micro-entity
  - comparative-ready micro-entity
  - loss-making
  - fixed-assets focused
  - creditor-heavy
- Added a management command:

```text
python manage.py build_companies_house_scenarios --strict
```

- Extended the iXBRL generator so accounts type wording is reflected in the generated accounts output.
- Added dormant account tagging so dormant scenarios produce `uk-bus:EntityDormantTruefalse` as true.
- Added Companies House status polling for existing submissions without creating duplicate submissions.
- Added audit events for status polling and scenario builds.
- Updated the Companies House workspace UI:
  - build local test scenarios button
  - scenario coverage matrix
  - iXBRL readiness display per scenario
  - check status button for submitted/pending filings
  - no credential values displayed

## Local Scenario Command

Command:

```text
docker exec ledgerhouse_web python manage.py build_companies_house_scenarios --strict
```

Result:

```text
All 8 Companies House local scenarios passed.
```

Each scenario validated:

- statutory draft created
- journal data is balanced at database level
- local XHTML/iXBRL generation succeeds
- local iXBRL validator passes
- readiness checks pass
- Companies House gateway XML can be built locally

## Automated Tests

Focused command:

```text
docker exec ledgerhouse_web python manage.py test accounting.tests.test_companies_house --noinput
```

Result:

```text
Ran 24 tests in 8.557s
OK
```

New coverage added:

- scenario builder creates all 8 accounts scenarios
- scenario builder marks valid drafts as iXBRL-ready
- dormant scenario contains dormant tagging
- management command reports success
- status polling updates stored submission status
- status polling creates audit trail
- workspace builds local scenarios without company lookup
- workspace polls existing submissions without resubmitting

Full regression command:

```text
docker exec ledgerhouse_web python manage.py test --noinput
```

Result:

```text
Ran 138 tests in 188.318s
OK
```

The full suite includes the six-tenant end-to-end workflow verification.

## Browser-Style Workspace Check

Command:

```text
docker exec ledgerhouse_web python manage.py shell -c "... Django test client GET /integrations/companies-house/ ..."
```

Result:

```text
status 200
has_scenarios True
has_build_button True
has_credentials False
```

## Boundary

The local Companies House preparation work is now broader and repeatable. The next external step remains Companies House review/confirmation from Ioan. Once they confirm the required test matrix, the exact requested scenarios can be submitted with unique incremental submission numbers.
