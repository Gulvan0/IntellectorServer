#!/usr/bin/env bash
# Restores the latest nightly dumps (main and sensitive) into scratch databases and sanity-checks them. Run as root.
set -euo pipefail
. "$(dirname "$0")/common.sh"

SCRATCH=intellector_restore_test
SENSITIVE_SCRATCH=intellector_restore_test_sensitive
LATEST="$(rclone lsf "$OFFSITE/db/" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.sql\.zst$' | sort | tail -1)"
[ -n "$LATEST" ] || { echo "No nightly dump found" >&2; exit 1; }
LATEST_SENSITIVE="${LATEST%.sql.zst}.sensitive.sql.zst"

trap 'mysql -e "DROP DATABASE IF EXISTS $SCRATCH; DROP DATABASE IF EXISTS $SENSITIVE_SCRATCH"' EXIT
mysql -e "DROP DATABASE IF EXISTS $SCRATCH; DROP DATABASE IF EXISTS $SENSITIVE_SCRATCH"
"$(dirname "$0")/restore.sh" "$LATEST" "$SCRATCH"
"$(dirname "$0")/restore.sh" "$LATEST_SENSITIVE" "$SENSITIVE_SCRATCH"

TABLES="$(mysql -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$SCRATCH'")"
VERSION="$(mysql -N -e "SELECT version_num FROM $SCRATCH.alembic_version")"
PLAYERS="$(mysql -N -e "SELECT COUNT(*) FROM $SCRATCH.player")"
[ "$TABLES" -ge 20 ] || { echo "Only $TABLES tables in the restored dump" >&2; exit 1; }
[ -n "$VERSION" ] || { echo "The restored dump has no Alembic revision" >&2; exit 1; }
[ "$PLAYERS" -gt 0 ] || { echo "The restored dump has no players" >&2; exit 1; }
PASSWORDS="$(mysql -N -e "SELECT COUNT(*) FROM $SENSITIVE_SCRATCH.playerpassword")"
[ "$PASSWORDS" -gt 0 ] || { echo "The restored sensitive dump has no passwords" >&2; exit 1; }
echo "Restore test of $LATEST passed: $TABLES tables, revision $VERSION, $PLAYERS players, $PASSWORDS passwords"
