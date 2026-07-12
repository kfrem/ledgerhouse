# LedgerHouse Local Verification Report

Date: 2026-07-12

## Local build status

- Hetzner server was deleted before this local build cycle; no cloud server is required for the checks below.
- Local Docker stack is running with:
  - `ledgerhouse_db` on PostgreSQL 16
  - `ledgerhouse_web` on Django development server at `http://localhost:8000/`
- Local login:
  - Username: `admin`
  - Password: `admin2`

## Built in this pass

- Client portal upload intake now accepts real files locally.
- CSV bank uploads import into `BankTransaction`.
- XLSX bank uploads are parsed through `openpyxl` and imported into `BankTransaction`.
- PDF/photos/other files are stored in the evidence vault through `EvidenceDocument`.
- Client management reports can be downloaded as CSV or PDF.
- Practice workspace remains separate at `/practice/`.
- Demo upload packs are generated for all seeded clients under `local_demo_files/`.
- Local backup/demo outputs are ignored by Git through `.gitignore`.

## Demo client data

Seeded clients:

- CareCo Limited
- CharityCo Foundation
- ConsultCo Consulting
- LogisticsCo Transport Ltd
- TechCo Software Ltd
- TradeCo Retail

Generated local files per client:

- `bank-statement-july.csv`
- `bank-statement-july.xlsx`
- `supplier-receipt.pdf`
- `expense-note.txt`

## Checklist coverage

| Area | Local status |
|---|---|
| App design and screens | Built and locally served |
| Login flows | Tested with redirect and authenticated access |
| Client portal logic | Tested |
| Accountant/practice workflows | Tested as separate `/practice/` workspace |
| File uploads | Tested for CSV, XLSX and PDF/evidence |
| Database logic | Tested on PostgreSQL |
| Docker build | Rebuilt successfully |
| PostgreSQL migrations | `makemigrations --check --dry-run` clean |
| Accounting calculations | Existing full suite passing |
| Reports | CSV and PDF generation tested |
| CSV/XLSX/PDF processing | Tested |
| Most automated tests | Full suite passed three times |

## Commands verified

- `docker compose up -d --build`
- `docker compose exec -T web python manage.py makemigrations --check --dry-run`
- `docker compose exec -T web python manage.py check`
- `docker compose exec -T web python manage.py seed_db`
- `docker compose exec -T web python manage.py build_demo_files`
- `docker compose exec -T web pytest accounting/tests/test_client_portal_workflows.py -q`
- `docker compose exec -T web pytest -q` repeated three times

## Test evidence

Focused workflow tests:

- `6 passed`

Full suite pass 1:

- `67 passed`

Full suite pass 2:

- `67 passed`

Full suite pass 3:

- `67 passed`

Observed warning:

- Django warns that `/app/staticfiles/` does not exist during local test middleware setup. This does not fail tests and does not affect local development serving. Production builds run `collectstatic`.

## External-only items not proven locally

The following still require a live external deployment or sandbox callbacks:

- Public HTTPS/domain behavior
- Real email deliverability
- HMRC/Open Banking production callback behavior
- Payment provider callbacks, if added later
- Public user access from outside the local machine
- Cloud firewall and deployment behavior
