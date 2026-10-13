#!/usr/bin/env bash
# Daily automated database backup & sync queue cleanup script for AI Billing
# Add to crontab with:
#   0 2 * * * /var/www/aibilling/deploy/backup_cron.sh >> /var/log/aibilling_backup.log 2>&1

set -o errexit
set -o pipefail

APP_DIR="${APP_DIR:-/var/www/aibilling}"
VENV_PYTHON="${VENV_PYTHON:-$APP_DIR/.venv/bin/python}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-aibilling.settings.production}"

cd "$APP_DIR"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Starting daily AI Billing maintenance..."

# 1. Create JSON database backup and prune backups older than 30 days
"$VENV_PYTHON" manage.py backup_db --retention-days=30

# 2. Purge processed offline sync queue entries older than 30 days
"$VENV_PYTHON" manage.py purge_sync_queue --days=30

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Maintenance completed successfully."
