# Companies House Test Filing Harness

Date: 2026-07-21

## Scope

Built and tested the local Companies House accounts filing path for LedgerHouse after receipt of the Companies House XML Gateway test account details. The credentials are stored outside Git and are not written into this report, tests, templates, status pages or committed code.

## Official Guidance Used

- Companies House Accounts Technical Interface Specification supplement 5.9, April 2026.
- Companies House XML Gateway TIS v5.3.
- Companies House XML Gateway accounts example and current gateway forum guidance for `FormSubmission-v2-11.xsd`.
- Companies House standalone iXBRL validator.

## Built Locally

- Added real XHTML/iXBRL micro/small unaudited accounts generation in `accounting/ixbrl.py`.
- Added FRC 2026 taxonomy namespaces and required Companies House/FRC facts for:
  - company name and registered number
  - period start/end and balance sheet date
  - accounting standards, accounts status and accounts type
  - unaudited/small companies regime statements
  - director approval/signing facts
  - average employees and core balance sheet/profit and loss facts
- Added local iXBRL validation checks before test filing.
- Added `CompaniesHouseFilingSubmission` model and migration.
- Added unique incremental submission-number tracking.
- Added Companies House XML Gateway accounts submission generation:
  - `Class` = `Accounts`
  - `Function` = `submit`
  - `GatewayTest` = `1`
  - `FormSubmission-v2-11.xsd`
  - default nested Companies House header namespace
  - base64 iXBRL accounts document in `Document/Data`
  - company number preserved consistently between form header and iXBRL
- Added gateway sender and response parser.
- Added pending-state handling for immediate `GetSubmissionStatus` polls where Companies House has not yet produced an accepted/rejected document result.
- Added request sanitisation so authentication values are stored as `REDACTED`.
- Added Companies House workspace UI action to send a test package.
- Added audit event creation for prepared and sent Companies House test submissions.

## External Tests Completed

### Companies House Standalone iXBRL Validator

Generated file:

```text
tmp/companies_house/ledgerhouse_accounts.xhtml
```

Result:

```text
Your file is valid.
```

The validator confirmed the generated iXBRL meets the iXBRL specification and Companies House business validation rules for the tested sample.

Latest passing validator file id:

```text
ae5346be-a44d-4676-9017-e8d96c3340a4
```

### Companies House XML Gateway

The earlier wrapper attempts were rejected while aligning the GovTalk/FormSubmission structure. The final corrected gateway submission was:

```text
Submission number: 000025
Gateway result: Submitted
Messages: none
```

The fix that moved the gateway past rejection was:

- use the current accounts gateway envelope shape
- use `FormSubmission-v2-11.xsd`
- serialize the nested `FormSubmission` with the Companies House header namespace as its default namespace
- preserve the leading zeroes in the Companies House company number so the form header and iXBRL match

Immediate status polling for submission `000025` returned pending/no accepted-or-rejected document yet, which is expected because Companies House accounts processing is asynchronous.

## Local Testing

### Focused Companies House Tests

Command:

```text
docker exec ledgerhouse_web python manage.py test accounting.tests.test_companies_house --noinput
```

Result:

```text
Ran 19 tests in 5.038s
OK
```

Covered:

- public Companies House API key status does not expose the key
- filing status reports test credential readiness without exposing presenter ID or authentication value
- company number normalisation
- public profile lookup request and error handling
- workspace display and local client creation
- GovTalk/FormSubmission XML contains v2.11 schema, package reference, test flag, function, form type key and six digit submission number
- nested Companies House namespace is serialized in the gateway-compatible form
- form header company number matches the iXBRL company number
- generated iXBRL is well formed and contains required accounts facts
- wrapper embeds decodable iXBRL accounts document
- XML sanitisation removes authentication value
- local submission numbers increment correctly
- readiness blockers prevent gateway send before iXBRL readiness
- successful mocked gateway sends store response and audit event
- immediate unprocessed status polls are treated as pending

### Full Regression

Command:

```text
docker exec ledgerhouse_web python manage.py test --noinput
```

Result:

```text
Ran 133 tests in 133.381s
OK
```

The full suite also completed the six-tenant end-to-end workflow verification.

## Security Checks

- Raw Companies House test credentials were not committed.
- Raw credentials were not written into this report.
- Gateway request XML stored in the database uses sanitised authentication values.
- Repository scan for the raw presenter ID and authentication value returned no matches.

## Current Boundary

The local iXBRL generation, local validation, Companies House standalone validator check, and XML Gateway test submission path are now working for the tested sample.

What remains is external Companies House review of the submitted test package and any follow-up test cases they ask for before issuing live software authorisation. Live production filing must not be claimed until Companies House approves the software/package reference for live use.
