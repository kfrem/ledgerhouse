# LedgerHouse Local Development Pass While Awaiting Authorisations

Date: 2026-07-16  
Environment: local Docker app at `http://127.0.0.1:8000/`  
Purpose: continue useful local development while HMRC, Companies House, payment-provider, legal and deployment authorisations remain external gates.

## Work Completed

### Client product experience

- Added a finance office status section to the client portal.
- Added plain-English operating health cards for gross profit, net margin and cash runway.
- Added a client-facing operating snapshot covering accounts department progress, reporting readiness, service queue, billing readiness and government service status.

### Practice workflow

- Added an account control section to the practice client file.
- Surfaced service, billing and integration readiness per client.
- Kept the practice view focused on the full client accounts department rather than a VAT-only workflow.

### Reports and calculations

- Extended management report calculations with:
  - cost of sales
  - overheads
  - gross profit
  - gross margin
  - net margin
  - cash runway months
- Added these metrics to the in-app management report.
- Added the new metrics to CSV and PDF report outputs.

### Local integration and SaaS readiness

- Added local operating status for billing provider readiness.
- Added local operating status for HMRC/Companies House readiness without requiring live approval.
- Kept live filing and live payment collection clearly separated from local readiness.

### Usability polish

- Added compact responsive cards for operating metrics.
- Verified the new panels render on the client portal, practice client file and management report screens.

## Automated Tests Run

### Django system check

Command:

```powershell
docker compose exec -T web python manage.py check
```

Result:

```text
System check identified no issues (0 silenced).
```

### Migration dry-run

Command:

```powershell
docker compose exec -T web python manage.py makemigrations --check --dry-run
```

Result:

```text
No changes detected
```

### Focused workflow tests

Command:

```powershell
docker compose exec -T web python manage.py test accounting.tests.test_client_portal_workflows
```

Result:

```text
Found 27 test(s).
Ran 27 tests in 19.251s
OK
```

### Full test suite

Command:

```powershell
docker compose exec -T web python manage.py test
```

Result:

```text
Found 109 test(s).
Ran 109 tests in 36.090s
OK
```

Expected local warning observed:

```text
accounting.W001 Database 'default' connects as a superuser or BYPASSRLS role.
```

This remains a production launch gate and is not a local development failure.

## Browser Smoke Test

The local web container was restarted so localhost reflected the latest code:

```powershell
docker compose restart web
docker compose exec -T web python manage.py check
```

Browser automation used installed Chrome:

```text
C:/Program Files/Google/Chrome/Application/chrome.exe
```

Login used:

```text
admin / admin2
```

Verified pages:

- `/`
- `/practice/clients/76168495-36f8-5eb6-9e25-fdce5c9213ef/`
- `/reports/76168495-36f8-5eb6-9e25-fdce5c9213ef/`

Browser assertions passed:

- client finance office status renders
- client gross profit renders
- client government services status renders
- practice account control renders
- practice local SaaS controls render
- report operating readiness renders
- report cash runway renders

## Remaining External Gates

The following remain outside local development and depend on third parties or production infrastructure:

- HMRC production approval and live filing.
- Companies House submission access, if live filing is required rather than public API lookup.
- Live Stripe/GoCardless keys and webhook verification.
- Final legal/commercial review.
- Public production deployment, DNS and HTTPS verification.
- Production restricted database role verification.

## Conclusion

Useful local work continued without using the paid server. The app now has stronger client-facing accounts department status, stronger practice-side account control, richer management reporting, local SaaS readiness visibility, and tested browser-visible output while external approvals remain pending.
