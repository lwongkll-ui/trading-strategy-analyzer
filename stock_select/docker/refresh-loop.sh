#!/bin/sh
# Regenerate the served page once on startup, then every weekday at 21:00 HKT.
# By 21:00 HKT both the Hang Seng same-day close and the prior US close have
# settled. Each run also advances the 7-day fundamentals cache toward full
# coverage (Yahoo throttles ~110 profiles/window; unresolved names retry next
# run), so daily spacing converges the cache without any manual babysitting.
set -u
export TZ=Asia/Hong_Kong
cd /app/stock_select

run() {
  echo "[$(date '+%F %T %Z')] refresh start"
  if python main.py --out /app/site/index.html; then
    echo "[$(date '+%F %T %Z')] refresh done"
  else
    echo "[$(date '+%F %T %Z')] refresh FAILED (exit $?)"
  fi
}

run   # build immediately so the page exists as soon as the stack comes up

while true; do
  now=$(date +%s)
  target=$(date -d "today 21:00" +%s)
  [ "$target" -le "$now" ] && target=$(date -d "tomorrow 21:00" +%s)
  sleep $((target - now))
  # Markets are shut at the weekend; skip Sat (6) and Sun (7).
  [ "$(date +%u)" -ge 6 ] || run
done
