# LedgerHouse Local Hardening Pass - 23 July 2026

## Purpose

Continue local reliability work while Companies House processes the four XML
Gateway test submissions. This pass did not enable production filing, live bank
feeds, external email delivery, payment collection or public deployment.

## Completed

### Local backup and restore rehearsal

- Added `accounting.local_backup`.
- Added `backup_local_database` management command.
- The command creates a ZIP archive containing a JSON fixture and a SHA-256
  manifest beneath Git-ignored `backups/`.
- The optional restore rehearsal deserializes all mutable records inside an
  atomic transaction and rolls it back. Immutable audit records are
  deserialized and counted but not re-saved into the same database because the
  database correctly blocks audit-log modification.
- A real local archive was created and rehearsed successfully:
  `backups/ledgerhouse-local-rehearsal-20260723.zip`.

### Bank-feed failure visibility

- The practice exception register now distinguishes an unmatched ordinary bank
  line from a bank-feed item where a suggested ledger match could not be found.
- The latter is displayed as `Investigate bank-feed match` with an explicit
  review instruction. It remains tenant-scoped and cannot silently disappear.

### Notification delivery controls

- Added durable attempt count, last error and next retry time fields to
  `NotificationEvent` through migration `0027`.
- Added bounded retry recording with a terminal failure state after three
  unsuccessful attempts.
- Added idempotent delivery recording that clears retry data and records an
  immutable audit event.
- The existing local mock-notification action now uses this controlled delivery
  path. It still does not claim that an external email has been sent.

### Documentation

- Updated `README.md` with the local backup/rehearsal command and its limit.

## Defect Found And Corrected

The first real restore rehearsal attempted to save existing immutable audit
events back into the same database. PostgreSQL correctly rejected that action.
The rehearsal now restores mutable records in a rollback-only transaction and
verifies immutable audit records by successful deserialization. A clean target
database restore can insert those audit records; the local same-database drill
must not overwrite them.

## Tests And Results

| Check | Result |
| --- | --- |
| `python manage.py migrate --noinput` | Migration `0027` applied successfully |
| Focused backup, notification, exception, banking and accounts suite | 25 passed |
| Real `backup_local_database --restore-rehearsal` | passed: 747 mutable records restored then rolled back; 221 immutable audit records deserialized |
| `python manage.py check --database default` | passed, no issues |
| `python manage.py makemigrations --check --dry-run` | passed, no changes detected |
| `python manage.py test --verbosity 1 --noinput` | 184 passed in 106.032 seconds |
| `python manage.py local_acceptance_suite --strict` | all client, practice, report, PDF and ZIP checks passed |
| `docker compose ps` | PostgreSQL healthy; web service serving port 8000 |
| Live local HTTP headers | client and practice routes redirected unauthenticated users to login; login returned `200`; CSP header was present on all checked routes |

## External Boundaries Remaining

1. Companies House must finish processing and review test submissions `000001`
   to `000004`; production filing stays disabled.
2. HMRC production approval and live taxpayer/agent authorisation.
3. A contracted bank-feed provider, consent flow and real account access.
4. An email provider, verified sending domain and delivery credentials.
5. Payment-provider account and webhook configuration.
6. Public deployment, DNS/TLS and a restore drill in the final hosted
   environment.
7. Legal and operational review before admitting public client data.
