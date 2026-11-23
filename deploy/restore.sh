#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: CONFIRM_RESTORE=YES $0 /absolute/path/to/backup.sqlite3" >&2
  exit 2
fi
if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Set CONFIRM_RESTORE=YES to stop the API and replace its database" >&2
  exit 2
fi

project_dir="${PROJECT_DIR:-/opt/dsb-backend-oracle}"
backup_file="$(realpath "$1")"
cd "$project_dir"
export COMPOSE_FILE="compose.yaml:compose.production.yaml"

# Preserve the current database off-instance before replacing it.
if [[ -f /etc/dsb-bot/backup.env ]]; then
  set -a
  # This root-owned file must contain only trusted KEY=value backup settings.
  source /etc/dsb-bot/backup.env
  set +a
fi
REQUIRE_OFFSITE_BACKUP=1 ./deploy/backup.sh

docker compose stop api
restart_api() {
  docker compose up -d api
}
trap restart_api EXIT

docker compose run --rm --no-deps --user 0:0 \
  --volume "$backup_file:/restore/input.sqlite3:ro" \
  --entrypoint python api -m dsb_bot.restore_db /restore/input.sqlite3 /data/dsb.sqlite3

restart_api
trap - EXIT
echo "Database restored from $backup_file"
