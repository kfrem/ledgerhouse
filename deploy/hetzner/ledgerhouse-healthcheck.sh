#!/usr/bin/env bash
# Small independent health probe for the LedgerHouse host. systemd captures
# failures in the journal, ready for a future alert transport configuration.

set -euo pipefail

container="${CONTAINER:-ledgerhouse_web}"
health_url="${HEALTH_URL:-http://127.0.0.1:8000/healthz/}"

docker inspect --format '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" |
  grep -qx 'true healthy'
curl --fail --silent --show-error --max-time 10 \
  -H 'X-Forwarded-Proto: https' "$health_url" | grep -qx '{"status": "ok"}'
