#!/bin/sh
# Capture screenshots, retrying while the provider's daily token budget refills.
#
# Checks the servers first. An earlier version assumed every failure was the token
# budget and retried for four hours against a backend that had been stopped — the
# retry was right about the symptom and wrong about the cause, and said nothing
# either way. A retry loop that cannot tell "wait" from "broken" wastes whichever
# one it is.
set -u
cd "$(dirname "$0")/.."

API="${API_URL:-http://localhost:8010}"
APP="${APP_URL:-http://localhost:3000}"
LOG=/tmp/crimlaw-shots.log

reachable() {
  curl -sf -o /dev/null --max-time 10 "$1"
}

for attempt in 1 2 3 4 5; do
  if ! reachable "$API/api/health"; then
    echo "backend not reachable at $API — start it before capturing:"
    echo "  cd backend && uv run uvicorn app.main:app --port 8010"
    exit 2
  fi
  if ! reachable "$APP"; then
    echo "frontend not reachable at $APP — start it before capturing:"
    echo "  cd frontend && npm run dev"
    exit 2
  fi

  echo "=== attempt $attempt ==="
  npm run --silent screenshots 2>&1 | tee "$LOG"
  if ! grep -q '✗' "$LOG"; then
    echo "all screenshots captured"
    exit 0
  fi
  if ! grep -qi 'rate limit\|429' "$LOG"; then
    echo "failed for a reason waiting will not fix — see $LOG"
    exit 1
  fi

  echo "token budget exhausted; waiting 20 minutes"
  sleep 1200
done

echo "gave up after 5 attempts"
exit 1
