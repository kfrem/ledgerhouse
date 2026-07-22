# LedgerHouse Assumptions Log

This is an append-only record of implementation decisions made where the
product specification did not provide a more detailed rule.

## A-001 | 2026-07-22 | Local build boundaries

LedgerHouse will treat HMRC, Companies House production filing, bank feeds,
email delivery, payments, public DNS/TLS and production backups as external
boundaries. Local code may provide interfaces and test doubles, but must make
their status visible and must not claim that a test double is a live service.

Reason: these services require third-party contracts, credentials, approvals
or real customer consent and cannot be truthfully completed by local code.

## A-002 | 2026-07-22 | Local data

Automated acceptance and demonstration workflows use synthetic tenants and
synthetic documents only. No real client data is introduced to make a local
test pass.

Reason: DECISIONS.md D-005 requires an explicit real-data admission gate.

## A-003 | 2026-07-22 | Accounting automation

Document classification and suggested nominal accounts remain proposals until
a practice user reviews and posts the resulting accounting entry. Automated
logic must not bypass evidence, approval, journal-balance or period-lock
controls.

Reason: this follows the rules-first/human-review accounting model in
DECISIONS.md D-002.
