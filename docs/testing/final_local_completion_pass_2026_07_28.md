# LedgerHouse Final Local Completion Pass - 28 July 2026

## Purpose

Run the remaining locally executable LedgerHouse verification work from a
rebuilt Docker image, correct any defect found during browser review, and
separate completed local evidence from external approval work.

## Local Work Completed

1. Rebuilt the Docker `web` image and recreated the local `web` and PostgreSQL
   services.
2. Applied all Django migrations and collected static assets from the rebuilt
   image.
3. Confirmed Django configuration, PostgreSQL use, migration state and Python
   package consistency.
4. Created a local database backup and performed a rollback-only restore
   rehearsal. The rehearsal deserialized 1,178 mutable records and validated
   343 immutable audit records before rolling the transaction back.
5. Ran the local production rehearsal. It verified tenant data, management
   report context, CSV export, two PDF outputs and the client data ZIP.
6. Ran all nine local Companies House/iXBRL scenarios, including the newly
   declared small unaudited filleted profile.
7. Ran the local acceptance suite covering client and practice pages, reports,
   CSV, PDF, management-pack, accounts-department-pack and data ZIP routes.
8. Reviewed responsive pages in a real browser at desktop and phone widths.

## Defect Found and Corrected

The phone-width client portal initially overflowed horizontally: the document
and report grid items retained their minimum-content width in a 375px viewport.

`static/accounting/dashboard.css` was corrected to allow client-grid items to
shrink and to stack/wrap report items and report actions at the mobile
breakpoint. The browser regression check after the correction showed a 375px
document width in a 375px viewport with zero overflowing elements. Desktop
layout continued to fit its viewport.

## Commands and Results

| Command / check | Result |
| --- | --- |
| `docker compose build web` and `docker compose up -d --force-recreate` | Pass; PostgreSQL healthy and web service on port 8000 |
| `python manage.py migrate --noinput` | Pass; no migrations outstanding |
| `python manage.py collectstatic --noinput` | Pass; 130 static files collected |
| `python manage.py check --database default` | Pass; no issues |
| `python manage.py makemigrations --check --dry-run` | Pass; no changes detected |
| `python -m pip check` | Pass; no broken requirements |
| `python manage.py backup_local_database --restore-rehearsal` | Pass; backup and rollback-only restore verified |
| `python manage.py local_production_rehearsal --strict` | Pass; all local rehearsal checks passed |
| `python manage.py test accounting.tests.test_static_assets` | Pass; 2 tests |
| `python manage.py test` | Pass; 186 tests in 62.936 seconds |
| `python manage.py build_companies_house_scenarios --strict` | Pass; 9 of 9 scenarios |
| `python manage.py local_acceptance_suite --strict` | Pass; all local acceptance checks |
| Browser, client portal at 390 x 844 | Pass; heading rendered and no horizontal overflow |
| Browser, practice dashboard at desktop width | Pass; heading rendered and no horizontal overflow |
| Browser, Companies House workspace | Pass; declared filing scope rendered |
| Browser, non-existent route | Pass; controlled 404 page rendered |

## Current Local State

- Docker is running locally at `http://127.0.0.1:8000/`.
- The local app is operational for the implemented client, practice, evidence,
  reporting, accounting workflow and Companies House preparation paths.
- The initial filing-scope guard accepts only MicroEntity, SmallUnaudited,
  SmallUnauditedFilleted, Dormant and AmendedMicroEntity. Unsupported types
  are rejected before a Companies House submission number is allocated.
- The four previously transmitted Companies House gateway tests remain
  `Pending`; this is not an acceptance result.

## External Work Deliberately Not Performed

The following cannot be honestly closed by local testing and were not sent or
enabled in this pass:

1. Send the prepared scope response to the Companies House XML Team and obtain
   confirmation on the planned filing types, including whether amended
   accounts count as a separate type for the requested next round.
2. Submit the first small-unaudited-filleted Gateway test and the second round
   of supported filing types. Each must use the next unique, incremental
   submission number after the XML Team confirms the scope.
3. Obtain Companies House formal authorisation before any production filing.
4. Complete HMRC sandbox OAuth with a VAT test user, then HMRC production
   approval before live tax filing.
5. Configure live bank feeds, payment collection, email delivery, public DNS,
   HTTPS and a deployed production environment. Each needs its own provider
   account, credentials and external proof.

## Conclusion

No additional local coding or local verification item was identified in this
pass. The next work is external integration and regulator/provider validation,
not a substitute for the completed local evidence.
