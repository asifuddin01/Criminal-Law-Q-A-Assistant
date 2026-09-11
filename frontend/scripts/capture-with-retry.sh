#!/bin/sh
# Capture screenshots, retrying while the provider's daily token budget refills.
#
# The free tier refills at roughly 8,000 tokens an hour and a full capture needs
# about 9,000, so a failed run is usually a matter of waiting rather than a fault.
set -u
cd "$(dirname "$0")/.."
attempt=1
while [ "$attempt" -le 5 ]; do
  echo "=== attempt $attempt ==="
  if npm run --silent screenshots 2>&1 | tee /tmp/crimlaw-shots.log; then
    if ! grep -q '✗' /tmp/crimlaw-shots.log; then
      echo "all screenshots captured"
      exit 0
    fi
  fi
  echo "incomplete — waiting 20 minutes for budget to refill"
  sleep 1200
  attempt=$((attempt + 1))
done
echo "gave up after $attempt attempts"
exit 1
