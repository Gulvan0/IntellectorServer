#!/usr/bin/env bash
# restore.sh <dump file name under db/> [target database, default: main]
# Loads the dump into the target database, which must not exist or be empty. Run as root (local socket).
set -euo pipefail
. "$(dirname "$0")/common.sh"

DUMP="${1:?usage: restore.sh <dump> [target_db]}"
TARGET="${2:-$MAIN_DB}"

mysql -e "CREATE DATABASE IF NOT EXISTS \`$TARGET\` CHARACTER SET utf8mb4"
if [ -n "$(mysql -N -e "SHOW TABLES FROM \`$TARGET\`")" ]; then
    echo "Database $TARGET is not empty. Drop and recreate it first." >&2
    exit 1
fi
rclone cat "$OFFSITE/db/$DUMP" | zstd -dc | mysql "$TARGET"
echo "Restored $DUMP into $TARGET"
