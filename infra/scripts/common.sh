# Sourced by the other scripts
OFFSITE="${OFFSITE:-B2:intellector-backup}"
export RCLONE_CONFIG="${RCLONE_CONFIG:-/srv/intellector/rclone.conf}"
OPS_ENV=/srv/intellector/ops.env   # HC_PING_URL=... (healthchecks.io), optional
MAIN_DB=main
[ -f "$OPS_ENV" ] && . "$OPS_ENV"

ping_healthcheck() {
    [ -n "${HC_PING_URL:-}" ] && curl -fsS -m 10 --retry 3 -o /dev/null "$HC_PING_URL" || true
}
