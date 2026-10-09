#!/usr/bin/env bash
# Local database backup for the LedgerHouse production host.
# This protects against an application/database mistake but is not an off-server
# disaster-recovery copy. Configure a separate encrypted off-server destination
# before onboarding client data.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/backups/ledgerhouse}"
KEEP_DAYS="${KEEP_DAYS:-14}"
CONTAINER="${CONTAINER:-ledgerhouse_db}"

install -d -m 700 "$BACKUP_DIR"
umask 077

exec 9>"$BACKUP_DIR/.backup.lock"
flock -n 9 || exit 0

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$BACKUP_DIR/ledgerhouse-${timestamp}.dump"
temporary="${destination}.partial"
trap 'rm -f "$temporary"' EXIT

docker exec "$CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary"
pg_restore -l "$temporary" >/dev/null
mv "$temporary" "$destination"
find "$BACKUP_DIR" -type f -name 'ledgerhouse-*.dump' -mtime +"$KEEP_DAYS" -delete
