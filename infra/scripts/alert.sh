#!/usr/bin/env bash
# alert.sh <failed unit>: tells the admin about it.
# Telegram first, through the Cloudflare Worker proxy (integrations.proxy in secret.yaml), since api.telegram.org is
# blocked from Russian hosts. If the proxy can't be reached either, a healthchecks.io check
# (HC_ALERT_URL in ops.env, e.g. https://hc-ping.com/<uuid>/fail) is pinged with the message instead, and forwards it
# to whatever integration is set up on that check
set -uo pipefail
. "$(dirname "$0")/common.sh"
UNIT="${1:?usage: alert.sh <unit>}"
SECRET=/srv/intellector/secret.yaml

TAIL="$(journalctl -u "$UNIT" -n 8 --no-pager -o cat 2>/dev/null | cut -c1-300)"
TEXT="$(hostname): $UNIT failed
$TAIL"

read -r PROXY_URL PROXY_KEY CHAT < <(python3 - "$SECRET" <<'PY'
import sys, yaml
integrations = yaml.safe_load(open(sys.argv[1]))["common"]["integrations"]
print(integrations["proxy"]["url"].rstrip("/"), integrations["proxy"]["key"], integrations["telegram"]["admin_chat_id"])
PY
)

PAYLOAD="$(python3 -c 'import json, sys; print(json.dumps({"chat_id": int(sys.argv[1]), "text": sys.argv[2]}))' "$CHAT" "$TEXT")"

# The worker (Telegram token held there) answers in VK's format, and reports some failures with HTTP 200: check the body
REPLY="$(curl -sS -m 10 -X POST "$PROXY_URL/method/messages.send?v=5.199&access_token=$PROXY_KEY" \
        -H 'Content-Type: application/json' --data-raw "$PAYLOAD" 2>/dev/null)"
if [[ "$REPLY" == '{"response":'* ]]; then
    exit 0
fi

if [ -n "${HC_ALERT_URL:-}" ]; then
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$TEXT" "$HC_ALERT_URL" && exit 0
fi

echo "No alert channel worked. $TEXT" >&2
exit 1
