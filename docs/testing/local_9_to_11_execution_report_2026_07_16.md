# LedgerHouse Local Development Pass 9-11

Date: 2026-07-16  
Scope: legal/commercial launch pack, production deployment readiness, and usability polish.  
Environment: local Docker application at `http://127.0.0.1:8000/`.

## Work Completed

### 9. Legal and commercial launch pack

- Expanded the public privacy page with clearer retention/deletion wording, integration/sub-processor coverage, and a security contact route.
- Expanded the public terms page with subscription/payment wording, customer responsibilities, support/availability expectations, and launch-status wording.
- Added a staff-only launch readiness centre at `/practice/launch/` so the practice can see which launch gates are already satisfied and which remain external.
- Added explicit readiness checks for:
  - public privacy notice
  - public service terms
  - final legal review
  - client invite acceptance
  - evidence intake
  - management reports
  - billing/subscription configuration
  - live payment keys
  - HMRC sandbox and production status
  - Companies House public API and filing access
  - Docker/postgres deployment status
  - production DNS/HTTPS status
  - restricted production database role

### 10. Production deployment readiness

- Added a deployment section inside the launch readiness centre rather than redeploying the server.
- The page now separates local readiness from external production gates. This is important because the user asked to keep server spend low until a client is ready to test externally.
- The deployment readiness checks identify the items that must be completed on the live server before public launch:
  - `DEBUG=False`
  - production HTTPS/DNS verification
  - restricted PostgreSQL application role
  - production payment keys
  - HMRC production approval
  - Companies House filing access, if the product will submit filings rather than only read public company data

### 11. Polish and usability

- Added a `Launch readiness` navigation path into the practice dashboard.
- Reworded practice screens away from technical/admin language:
  - `Admin fallback` was replaced with `System records`
  - `Admin record` was replaced with `System record`
  - direct Django admin wording was removed from customer-facing/practice templates
- Kept the client and practice flows focused on an accounts department model rather than a VAT-only tool.

## Automated Checks Run

### Django system check

Command:

```powershell
docker compose exec -T web python manage.py check
```

Result: passed.

Output summary:

```text
System check identified no issues (0 silenced).
```

### Migration dry-run

Command:

```powershell
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result: passed.

Output summary:

```text
No changes detected
```

### Focused client/practice workflow tests

Command:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows
```

Result: passed.

Output summary:

```text
Found 27 test(s).
Ran 27 tests in 18.504s
OK
```

### Full test suite

Command:

```powershell
docker compose exec -T web python manage.py test
```

Result: passed.

Output summary:

```text
Found 109 test(s).
Ran 109 tests in 35.168s
OK
```

Expected warning observed:

```text
accounting.W001 Database 'default' connects as a superuser or BYPASSRLS role.
```

This warning is acceptable for local development and is now represented as a production launch gate. It must be resolved before public deployment by running the restricted database-role deployment path and connecting production with that role.

## Browser Smoke Test

Tooling: Playwright through installed Chrome at:

```text
C:/Program Files/Google/Chrome/Application/chrome.exe
```

Login used:

```text
admin / admin2
```

Pages checked:

- `/practice/launch/`
- `/privacy/`
- `/terms/`

Assertions passed:

- launch readiness centre renders
- customer/legal pack section renders
- deployment gate section renders
- HMRC production approval gate renders
- privacy retention section renders
- privacy security contact section renders
- terms payments/subscriptions section renders
- terms launch status section renders

## Remaining External Gates

These cannot be fully completed locally:

- final legal review of privacy/terms/commercial commitments
- HMRC production approval decision by HMRC
- Companies House submission access if live filing is required
- live payment-provider credentials and webhook verification
- public DNS/HTTPS verification on the production server
- production database restricted-role connection verification

## Conclusion

Items 9 to 11 are complete for local development. The product now has an in-app launch readiness centre, stronger public legal/commercial pages, clearer production gates, and less technical practice-facing language. The local application passed system checks, migration checks, focused workflow tests, full tests, and browser smoke checks.
