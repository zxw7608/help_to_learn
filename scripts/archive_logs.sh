#!/bin/sh
# archive_logs.sh
# Runs on the 1st of each month (via cron or supervisord trigger).
# - Compresses last month's rotated log files into a monthly .tar.gz archive
# - Deletes archives older than 3 months
# - Appends a summary line to /app/logs/archive.log for auditability

set -e

LOG_DIR="/app/logs"
ARCHIVE_DIR="/app/logs/archives"
AUDIT_LOG="$LOG_DIR/archive.log"

mkdir -p "$ARCHIVE_DIR"

# ── Figure out last month ────────────────────────────────────────────────────
# date -d is GNU-only; use python for portability inside the container
LAST_MONTH=$(python3 -c "
from datetime import date, timedelta
today = date.today()
first = today.replace(day=1)
last_month = first - timedelta(days=1)
print(last_month.strftime('%Y-%m'))
")

ARCHIVE_NAME="logs_${LAST_MONTH}.tar.gz"
ARCHIVE_PATH="$ARCHIVE_DIR/$ARCHIVE_NAME"

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [archive_logs] Archiving logs for $LAST_MONTH..." >> "$AUDIT_LOG"

# Collect rotated files that match last month (e.g. worker.log.1 modified last month,
# or any file whose name contains the month stamp).
# Strategy: find all *.log.* (rotated backups) modified in the previous calendar month.
TMPLIST=$(mktemp)
find "$LOG_DIR" -maxdepth 1 -name "*.log.*" \
    -newer /dev/null \
    | while read -r f; do
        # Keep only files whose last-modified month matches LAST_MONTH
        FILE_MONTH=$(python3 -c "
import os, datetime
t = os.path.getmtime('$f')
print(datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m'))
")
        if [ "$FILE_MONTH" = "$LAST_MONTH" ]; then
            echo "$f"
        fi
    done > "$TMPLIST"

FILE_COUNT=$(wc -l < "$TMPLIST" | tr -d ' ')

if [ "$FILE_COUNT" -gt 0 ]; then
    # shellcheck disable=SC2046
    tar -czf "$ARCHIVE_PATH" $(cat "$TMPLIST")
    # Remove the original rotated files after successful archiving
    while IFS= read -r f; do
        rm -f "$f"
    done < "$TMPLIST"
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [archive_logs] Created $ARCHIVE_NAME ($FILE_COUNT files)" >> "$AUDIT_LOG"
else
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [archive_logs] No rotated log files found for $LAST_MONTH — skipping archive" >> "$AUDIT_LOG"
fi

rm -f "$TMPLIST"

# ── Delete archives older than 3 months ─────────────────────────────────────
CUTOFF=$(python3 -c "
from datetime import date, timedelta
today = date.today()
# Go back ~92 days to cover 3 full months
cutoff = today.replace(day=1)
for _ in range(3):
    cutoff = (cutoff - timedelta(days=1)).replace(day=1)
print(cutoff.strftime('%Y-%m'))
")

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [archive_logs] Removing archives older than $CUTOFF..." >> "$AUDIT_LOG"

find "$ARCHIVE_DIR" -name "logs_*.tar.gz" | while read -r archive; do
    # Extract YYYY-MM from filename like logs_2025-01.tar.gz
    ARCH_MONTH=$(basename "$archive" | sed 's/logs_\([0-9]\{4\}-[0-9]\{2\}\)\.tar\.gz/\1/')
    if [ "$ARCH_MONTH" \< "$CUTOFF" ]; then
        rm -f "$archive"
        echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [archive_logs] Deleted old archive: $(basename "$archive")" >> "$AUDIT_LOG"
    fi
done

echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [archive_logs] Done." >> "$AUDIT_LOG"
