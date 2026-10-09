# LedgerHouse No-HMRC Local Completion Pack - 2026-07-21

## Scope

This pass completed local LedgerHouse work that does not require HMRC approval, HMRC credentials, live tax submission, bank-feed approval, payments, DNS or deployment. It focused on making the local accounts department build auditable and handover-ready.

## Built

1. `accounting/local_completion.py` service.
2. `build_no_hmrc_completion_pack` management command.
3. Twelve-item no-HMRC build register.
4. Tenant readiness CSV export.
5. Developer takeover `README.md`.
6. Per-tenant management report CSV export.
7. Per-tenant management report PDF export.
8. Per-tenant management pack PDF export.
9. Per-tenant accounts department pack PDF export.
10. Per-tenant client data ZIP export.
11. Audit event for each local completion pack build.
12. Automated tests proving the pack builds and strict mode passes.

## Continuation Update

Additional local app work was completed after the initial pack:

1. Added `build_no_hmrc_completion_zip` to generate a single ZIP bundle from the local completion pack.
2. Added staff-only download view `download_no_hmrc_completion_pack`.
3. Added route `/practice/accounts-department/no-hmrc-pack/`.
4. Added a visible `No-HMRC handover ZIP` action to the accounts department suite.
5. Added tests for the ZIP contents.
6. Added tests that practice staff can download the ZIP from the app.
7. Added tests that client users cannot download the practice handover ZIP.

## Real Local Pack Generated

Command:

```powershell
docker exec ledgerhouse_web python manage.py build_no_hmrc_completion_pack --strict --username loop-engineering
```

Result:

- 15 local clients/scenario companies processed.
- Every listed tenant returned `8/8 local phases`.
- Output written to:

`output/no_hmrc_completion`

Key files:

- `output/no_hmrc_completion/README.md`
- `output/no_hmrc_completion/tenant_readiness.csv`
- `output/no_hmrc_completion/local_no_hmrc_build_items.json`
- Per-client `management_report.csv`
- Per-client `management_report.pdf`
- Per-client `management_pack.pdf`
- Per-client `accounts_department_pack.pdf`
- Per-client `client_data_export.zip`

## Tests Run

Focused accounts department suite:

```powershell
docker exec ledgerhouse_web python manage.py test accounting.tests.test_accounts_department_suite --noinput
```

Result:

Initial result:

`Ran 9 tests in 6.714s - OK`

Continuation result:

`Ran 12 tests in 18.819s - OK`

Full regression:

```powershell
docker exec ledgerhouse_web python manage.py test --noinput
```

Result:

Initial result:

`Ran 145 tests in 158.420s - OK`

Continuation result:

`Ran 148 tests in 206.192s - OK`

## Browser Smoke Check

Checked:

`http://127.0.0.1:8000/practice/accounts-department/`

Confirmed visible:

- Accounts department suite.
- Debtors and credit control.
- Suppliers and payment runs.
- Close, assets and review sign-off.
- PAYE, CIS and corporation tax.
- Draft accounts and filing readiness.
- Tasks and mock notifications.
- What has working records now.
- No-HMRC handover ZIP.

Layout check:

- No horizontal overflow detected.

Download route checked in automated tests:

`/practice/accounts-department/no-hmrc-pack/`

## Remaining External Blockers Only

- HMRC live filing approval and production OAuth.
- Companies House live filing approval and production enablement.
- Bank-feed provider access.
- Payment provider setup.
- DNS/server deployment.
- Legal/compliance review where production trading requires it.

## Developer Takeover Notes

Another developer should begin by opening:

1. `output/no_hmrc_completion/README.md`
2. `output/no_hmrc_completion/tenant_readiness.csv`
3. `docs/testing/no_hmrc_local_completion_pack_2026_07_21.md`
4. `docs/testing/companies_house_local_completion_controls_2026_07_21.md`

Before changing live integration code, run:

```powershell
docker exec ledgerhouse_web python manage.py test --noinput
```

Before handover, refresh the local pack:

```powershell
docker exec ledgerhouse_web python manage.py build_no_hmrc_completion_pack --strict --username loop-engineering
```

## Conclusion

The local no-HMRC LedgerHouse accounts department work is now evidence-backed. The application can generate local client operating data, run the accounts department workflow, export reports and packs, and produce a developer takeover bundle without depending on HMRC.
