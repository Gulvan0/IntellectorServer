#!/usr/bin/env bash
# Runs every minute. Restarts the server after 3 consecutive failed /health checks.
set -uo pipefail

COUNTER=/run/intellector-watchdog.failures
URL=http://127.0.0.1:${PORT:-8000}/health

# a server stopped on purpose (ictl stop) or still starting up is not a failure
systemctl is-active --quiet intellector-server.service || { rm -f "$COUNTER"; exit 0; }

if curl -fsS -m 5 -o /dev/null "$URL"; then
    rm -f "$COUNTER"
    exit 0
fi

FAILURES=$(( $(cat "$COUNTER" 2>/dev/null || echo 0) + 1 ))
echo "$FAILURES" > "$COUNTER"
echo "Health check failed ($FAILURES in a row)"
if [ "$FAILURES" -ge 3 ]; then
    rm -f "$COUNTER"
    systemctl restart intellector-server.service
    exit 1  # raises the alert
fi
