#!/usr/bin/env bash
# alert.sh <failed unit>: tells the admin about it.
# Telegram first; api.telegram.org is blocked from Russian hosts, so if it can't be reached, a healthchecks.io check
# (HC_ALERT_URL in ops.env, e.g. https://hc-ping.com/<uuid>/fail) is pinged with the message instead, and forwards it
# to whatever integration is set up on that check
set -uo pipefail
. "$(dirname "$0")/common.sh"
UNIT="${1:?usage: alert.sh <unit>}"
SECRET=/srv/intellector/secret.yaml

TAIL="$(journalctl -u "$UNIT" -n 8 --no-pager -o cat 2>/dev/null | cut -c1-300)"
TEXT="$(hostname): $UNIT failed
$TAIL"

read -r TOKEN CHAT < <(python3 - "$SECRET" <<'PY'
import sys, yaml
telegram = yaml.safe_load(open(sys.argv[1]))["common"]["integrations"]["telegram"]
print(telegram["token"], telegram["admin_chat_id"])
PY
)

if curl -fsS -m 8 -o /dev/null "https://api.telegram.org/bot$TOKEN/sendMessage" \
        --data-urlencode "chat_id=$CHAT" --data-urlencode "text=$TEXT"; then
    exit 0
fi

if [ -n "${HC_ALERT_URL:-}" ]; then
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$TEXT" "$HC_ALERT_URL" && exit 0
fi

echo "No alert channel worked. $TEXT" >&2
exit 1
