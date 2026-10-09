# LedgerHouse Companies House Local Completion Controls - 2026-07-21

## Scope

This pass addressed the outstanding local Companies House work that can be completed before Companies House confirms production approval. It does not claim live filing approval. Live filing remains externally blocked until Companies House reviews the submitted gateway tests and confirms the route is approved.

## Built In This Pass

1. Poll history ledger: every Companies House status poll is now stored in `CompaniesHouseSubmissionPoll`.
2. Filing approval gate: each statutory accounts draft can now have a `CompaniesHouseApprovalGate`.
3. Practice signoff control: a ready statutory accounts draft can be signed off locally before test submission.
4. Client approval linkage: the Companies House gate is linked to a `ClientApprovalRecord`.
5. Production safety lock: the status panel now states `Test mode only` unless explicit live settings and approval flags are configured.
6. Rejection action mapping: gateway rejection messages are translated into practical correction actions.
7. Evidence ZIP export: `build_companies_house_evidence_pack` creates a reviewer pack.
8. Scenario matrix export: local scenario results are exported as CSV and JSON.
9. Sanitized XML export: generated gateway XML samples are included without raw authentication values.
10. iXBRL sample export: generated XHTML/iXBRL samples are included for local review.
11. Technical and plain-English evidence notes: the ZIP includes `README.md` explaining the controls and boundaries.
12. Workspace UI controls: the Companies House page now displays the production lock, filing gates, poll history, rejection actions and the 12-item register.

## Files Changed

- `accounting/models.py`
- `accounting/migrations/0023_companies_house_controls.py`
- `accounting/admin.py`
- `accounting/companies_house.py`
- `accounting/companies_house_evidence.py`
- `accounting/management/commands/build_companies_house_evidence_pack.py`
- `accounting/views.py`
- `templates/accounting/companies_house_workspace.html`
- `accounting/tests/test_companies_house.py`

## Evidence Pack

Generated:

`output/companies_house/ledgerhouse_companies_house_evidence_pack.zip`

Contents include:

- `README.md`
- `scenario_matrix.csv`
- `scenario_matrix.json`
- `submissions.csv`
- `poll_history.csv`
- `approval_gates.csv`
- `next_12_local_items.json`
- `ixbrl/*.xhtml`
- `gateway_xml/*.xml` or blocked notes where applicable

The pack was checked for accidental raw credential exposure by the automated test suite. The repository scan found only fake test values inside tests, not the real Companies House or HMRC secrets.

## Commands Run

```powershell
docker exec ledgerhouse_web python manage.py test accounting.tests.test_companies_house --noinput
```

Result:

`Ran 29 tests in 14.361s - OK`

```powershell
docker exec ledgerhouse_web python manage.py migrate --noinput
```

Result:

`Applying accounting.0023_companies_house_controls... OK`

```powershell
docker exec ledgerhouse_web python manage.py build_companies_house_evidence_pack --username loop-engineering
```

Result:

`Companies House evidence pack written to output/companies_house/ledgerhouse_companies_house_evidence_pack.zip`

```powershell
docker exec ledgerhouse_web python manage.py test --noinput
```

Result:

`Ran 143 tests in 159.247s - OK`

## Browser UI Smoke Check

Rendered page checked:

`http://127.0.0.1:8000/integrations/companies-house/`

Confirmed visible:

- Companies House workspace title.
- Production safety lock.
- Client approval and practice signoff gates.
- Accounts scenarios ready before Companies House review.
- Recent Companies House filing tests.
- Twelve Companies House items completed without external approval.

Layout check:

- No horizontal overflow detected in the browser check.

## Local Data Checks

```powershell
docker exec ledgerhouse_web python manage.py shell -c "from pathlib import Path; p=Path('output/companies_house/ledgerhouse_companies_house_evidence_pack.zip'); print(p.exists(), p.stat().st_size if p.exists() else 0)"
```

Result:

`True 55802`

```powershell
docker exec ledgerhouse_web python manage.py shell -c "from accounting.companies_house_scenarios import companies_house_scenario_summary; s=companies_house_scenario_summary(); print(len(s)); print(all(x['ixbrl_ready'] for x in s));"
```

Result:

`8` and `True`

```powershell
docker exec ledgerhouse_web python manage.py shell -c "from accounting.companies_house import companies_house_status; s=companies_house_status(); print(s['production_safety_lock']); print(s['test_mode_only']);"
```

Result:

`Test mode only` and `True`

## Remaining External Blockers Only

- Companies House review/confirmation of required XML Gateway test submissions.
- Companies House production/live filing credentials and explicit live enablement.
- HMRC live filing approval for HMRC-specific routes.
- Bank feed, payment provider, DNS/server deployment and legal review where those services are required.

## Conclusion

All locally buildable Companies House filing controls identified in this pass were implemented and tested. The local application can now generate and evidence scenario accounts, maintain filing gate records, persist status polling, explain rejection actions, export a sanitized review pack, and keep production filing locked until external approval is actually obtained.
