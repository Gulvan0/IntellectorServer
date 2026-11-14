#!/usr/bin/env bash
# Dumps the main database offsite as db/<YYYY-MM-DD>.sql.zst, and the sensitive one as db/<YYYY-MM-DD>.sensitive.sql.zst.
#   --if-pending-migrations   dumps as db/pre-deploy-<YYYY-MM-DD-HHMM>-<sha>.sql.zst, and only if the schema is behind
#                             the release in `current` (run before the migrations of a starting server)
set -euo pipefail
. "$(dirname "$0")/common.sh"

CURRENT=/srv/intellector/server/current
SHA="$(cat "$CURRENT/REVISION" 2>/dev/null || echo unknown)"

if [ "${1:-}" = "--if-pending-migrations" ]; then
    # a brand new database has nothing worth keeping
    if ! mysql --defaults-extra-file=/srv/intellector/mysql-backup.cnf -N -e "SHOW TABLES FROM $MAIN_DB" | grep -q .; then
        exit 0
    fi
    cd "$CURRENT"  # the configuration is found relative to the working directory
    STAGE=prod venv/bin/alembic current 2>/dev/null | grep -q "(head)" && exit 0
    NAME="pre-deploy-$(date -u +%Y-%m-%d-%H%M)-$SHA"
    PING=no
else
    NAME="$(date -u +%Y-%m-%d)"
    PING=yes
fi

TMP="$(mktemp /var/tmp/intellector-dump.XXXXXX)"
trap 'rm -f "$TMP"' EXIT

dump() { # <database> <file name under db/>
    # written to disk first: a dump that failed halfway must never reach the offsite storage
    mysqldump --defaults-extra-file=/srv/intellector/mysql-backup.cnf \
        --single-transaction --quick --routines --triggers --events --no-tablespaces "$1" | zstd -q -3 -o "$TMP" -f
    rclone copyto "$TMP" "$OFFSITE/db/$2"

    local size
    size="$(rclone lsf --format s --include "$2" "$OFFSITE/db/")"
    [ "$size" = "$(stat -c %s "$TMP")" ] || { echo "Uploaded dump size mismatch" >&2; exit 1; }
    echo "Uploaded db/$2 ($size bytes)"
}

dump "$MAIN_DB" "$NAME.sql.zst"
dump "$SENSITIVE_DB" "$NAME.sensitive.sql.zst"
[ "$PING" = yes ] && ping_healthcheck
exit 0
