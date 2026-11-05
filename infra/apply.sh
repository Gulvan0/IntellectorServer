#!/usr/bin/env bash
# Copies the configs from this folder into place; idempotent. Run as root (deploy.py does so through sudo).
#   --check   prints what differs from the installed files and changes nothing
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK=no
[ "${1:-}" = "--check" ] && CHECK=yes
CHANGED=()
NEED_DAEMON_RELOAD=no
NEED_CADDY_RELOAD=no
NEED_JOURNALD_RESTART=no
NEED_MYSQL_NOTICE=no

install_file() { # source destination mode
    if [ -f "$2" ] && cmp -s "$1" "$2"; then
        return 1
    fi
    CHANGED+=("$2")
    if [ "$CHECK" = yes ]; then
        diff -u --label "installed:$2" --label "repo:$1" "$2" "$1" 2>/dev/null || echo "+ new file $2"
    else
        install -D -m "$3" "$1" "$2"
    fi
    return 0
}

for unit in "$HERE"/systemd/*; do
    install_file "$unit" "/etc/systemd/system/$(basename "$unit")" 644 && NEED_DAEMON_RELOAD=yes
done
install_file "$HERE/caddy/Caddyfile" /etc/caddy/Caddyfile 644 && NEED_CADDY_RELOAD=yes
install_file "$HERE/mysql/intellector.cnf" /etc/mysql/conf.d/intellector.cnf 644 && NEED_MYSQL_NOTICE=yes
install_file "$HERE/journald/intellector.conf" /etc/systemd/journald.conf.d/intellector.conf 644 && NEED_JOURNALD_RESTART=yes
ln -sfn "$HERE/ictl" /usr/local/bin/ictl 2>/dev/null || true

if [ "$CHECK" = yes ]; then
    echo "${#CHANGED[@]} file(s) differ"
    exit 0
fi

[ "$NEED_DAEMON_RELOAD" = yes ] && systemctl daemon-reload
[ "$NEED_JOURNALD_RESTART" = yes ] && systemctl restart systemd-journald
systemctl enable intellector.target intellector-backup.timer intellector-restore-test.timer \
    intellector-log-archive.timer intellector-watchdog.timer intellector-server.service >/dev/null

# Caddy is reloaded only on Caddyfile changes (it closes the open WebSockets), and only if it is meant to run:
# it stays disabled until v1 gives up ports 80 and 443
if [ "$NEED_CADDY_RELOAD" = yes ] && systemctl is-enabled --quiet caddy; then
    caddy validate --config /etc/caddy/Caddyfile
    systemctl reload caddy
fi
[ "$NEED_MYSQL_NOTICE" = yes ] && echo "mysql config changed: it applies at the next MySQL restart (systemctl restart mysql)"
echo "Applied: ${#CHANGED[@]} file(s) changed"
