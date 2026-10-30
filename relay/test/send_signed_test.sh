#!/bin/bash
# usage: RELAY_URL=https://<relay>/api/twitch send_signed_test.sh <message_id> <test_id>
# secret 從 .relay_secrets.env 讀，不輸出
set -e
if [ -z "${RELAY_URL:-}" ]; then echo "錯誤：請設定 RELAY_URL（例如 https://<relay>/api/twitch）" >&2; exit 2; fi
if [ $# -lt 2 ]; then echo "用法：RELAY_URL=... $0 <message_id> <test_id>" >&2; exit 2; fi
 cd "$(dirname "$0")/.."; set -a; . ./.relay_secrets.env; set +a
MID="$1"; TID="$2"; TS=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
BODY="{\"grokbot_test\":\"$TID\",\"subscription\":{\"type\":\"grokbot.test\"}}"
SIG="sha256=$(printf '%s' "$MID$TS$BODY" | openssl dgst -sha256 -hmac "$TWITCH_EVENTSUB_SECRET" -r | cut -d' ' -f1)"
curl -s -o /dev/stderr -w "HTTP %{http_code}\n" -X POST "$RELAY_URL" \
 -H "content-type: application/json" -H "Twitch-Eventsub-Message-Id: $MID" -H "Twitch-Eventsub-Message-Timestamp: $TS" \
 -H "Twitch-Eventsub-Message-Signature: $SIG" -H "Twitch-Eventsub-Message-Type: notification" -d "$BODY"
