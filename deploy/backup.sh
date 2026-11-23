#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:-/var/backups/dsb-backend-oracle}"
project_dir="${PROJECT_DIR:-/opt/dsb-backend-oracle}"
backup_name="dsb-$(date -u +%Y%m%dT%H%M%SZ)-$$.sqlite3"

install -d -m 0700 "$backup_dir"
cd "$project_dir"

# SQLite's online backup API produces a consistent snapshot while the API is live.
docker compose exec -T api python -c \
  'import sqlite3; source = sqlite3.connect("/data/dsb.sqlite3"); target = sqlite3.connect("/data/backup.sqlite3"); source.backup(target); result = target.execute("PRAGMA integrity_check").fetchone(); target.close(); source.close(); assert result == ("ok",), result'
docker compose cp "api:/data/backup.sqlite3" "$backup_dir/$backup_name"
docker compose exec -T api rm -f /data/backup.sqlite3
chmod 0600 "$backup_dir/$backup_name"

if [[ -n "${OCI_BACKUP_BUCKET:-}" ]]; then
  command -v oci >/dev/null || {
    echo "OCI CLI is required when OCI_BACKUP_BUCKET is configured" >&2
    exit 1
  }
  oci os object put \
    --auth instance_principal \
    --bucket-name "$OCI_BACKUP_BUCKET" \
    --name "$backup_name" \
    --file "$backup_dir/$backup_name" \
    --no-multipart \
    --no-overwrite \
    --verify-checksum \
    >/dev/null
elif [[ "${REQUIRE_OFFSITE_BACKUP:-0}" == "1" ]]; then
  echo "OCI_BACKUP_BUCKET is required for the configured offsite backup policy" >&2
  exit 1
else
  echo "WARNING: only a local backup was created; configure offsite backup before production" >&2
fi

# Keep a short local recovery window. Configure a separate off-instance copy before production.
find "$backup_dir" -maxdepth 1 -type f -name 'dsb-*.sqlite3' -mtime +30 -delete
printf 'Created SQLite backup: %s\n' "$backup_dir/$backup_name"
