# Companies House integration pass - 2026-07-13

## Scope

- Confirmed the logged-in Companies House Developer Hub account has an existing live `Practice App`.
- Stored the existing REST API key in `C:\Users\kfrem\.companies_house_api_key`, outside the repository.
- Added a local Companies House public data API client using Basic auth with the API key as username.
- Added `/integrations/companies-house/` for practice users to look up a company by number.
- Added an action to create or match a LedgerHouse client record from the official company profile.
- Added audit logging for Companies House client sync actions.

## Official API basis

- Companies House requires an account and API credentials for API use.
- Public company profile lookup is `GET /company/{companyNumber}`.
- The public company profile endpoint requires API key authentication.
- Companies House Basic auth uses the API key as the username and leaves the password blank.

## Verification checklist

- API key is local-only and not committed.
- Settings support `COMPANIES_HOUSE_API_KEY` for production and `COMPANIES_HOUSE_API_KEY_FILE` for local development.
- Company number input is normalised before API calls.
- API failures are converted into controlled UI messages.
- The page can show official company status, type, incorporation date, filing dates, SIC codes and registered office.
- Creating a client from Companies House creates default nominal accounts and an audit event.

## Commands run

These commands were run after implementation:

```powershell
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web pytest accounting/tests/test_companies_house.py -q
docker compose exec -T web pytest accounting/tests/test_hmrc_sandbox.py accounting/tests/test_client_portal_workflows.py -q
docker compose exec -T web pytest -q
docker compose up -d web
docker compose exec -T web python manage.py check
docker compose exec -T web pytest accounting/tests/test_companies_house.py -q
docker compose exec -T web python manage.py shell -c "<localhost Companies House live lookup smoke>"
```

## Results

- `manage.py check` passed before and after the web container restart.
- `makemigrations --check --dry-run` reported no model changes.
- Companies House focused tests passed: 6/6.
- Adjacent HMRC/practice workflow tests passed: 36/36.
- Full test suite passed: 103/103.
- Live API smoke check passed against Companies House company number `00000006`.
- Local authenticated page smoke passed at `/integrations/companies-house/?company_number=00000006`.

## Production note

This is a read-only Companies House public data integration. Actual software filing to Companies House is still a separate production filing capability and should not be treated as enabled by this API key alone.
