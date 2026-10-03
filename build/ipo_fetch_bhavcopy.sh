#!/bin/bash
# Pull one NSE bhavcopy per trading day and reduce it to the five fields we need.
# Two formats: the old per-month archive up to 2024, the UDiFF file from 2024 on.
# Holidays 404 and are skipped silently; that is how we learn the trading calendar.
SP="$(cd "$(dirname "$0")" && pwd)"
OUT="$SP/day"
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

one() {
  d=$1                                    # yyyymmdd
  [ -s "$OUT/$d.txt" ] && return 0        # already have it
  Y=${d:0:4}; M=${d:4:2}; D=${d:6:2}
  MON=$(date -j -f "%Y%m%d" "$d" "+%b" 2>/dev/null | tr '[:lower:]' '[:upper:]')
  tmp=$(mktemp -d); z="$tmp/f.zip"

  if [ "$d" -ge 20240101 ]; then
    url="https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_${d}_F_0000.csv.zip"
  else
    url="https://nsearchives.nseindia.com/content/historical/EQUITIES/${Y}/${MON}/cm${D}${MON}${Y}bhav.csv.zip"
  fi

  code=$(curl -s -o "$z" -w "%{http_code}" --max-time 60 \
         -H "User-Agent: $UA" -H "Referer: https://www.nseindia.com/" "$url")
  if [ "$code" != "200" ] || [ ! -s "$z" ]; then rm -rf "$tmp"; return 1; fi
  unzip -o -q "$z" -d "$tmp" 2>/dev/null || { rm -rf "$tmp"; return 1; }
  csv=$(ls "$tmp"/*.csv 2>/dev/null | head -1)
  [ -z "$csv" ] && { rm -rf "$tmp"; return 1; }

  # Normalise both layouts to: ISIN|SYMBOL|CLOSE|PREVCLOSE
  if [ "$d" -ge 20240101 ]; then
    awk -F, 'NR>1 && $7!="" { print $7 "|" $8 "|" $18 "|" $20 "|" $9 }' "$csv" > "$OUT/$d.txt"
  else
    awk -F, 'NR>1 && $13!="" { gsub(/ /,"",$13); print $13 "|" $1 "|" $6 "|" $8 "|" $2 }' "$csv" > "$OUT/$d.txt"
  fi
  rm -rf "$tmp"
  [ -s "$OUT/$d.txt" ] || return 1
  return 0
}
export -f one; export OUT UA

# every calendar day in range; weekends and holidays simply 404
python3 - <<'PY' > /tmp/alldates.txt
from datetime import date, timedelta
d, end = date(2021,10,1), date(2026,10,1)
while d <= end:
    if d.weekday() < 5: print(d.strftime('%Y%m%d'))
    d += timedelta(days=1)
PY
total=$(wc -l < /tmp/alldates.txt | tr -d ' ')
echo "trading-day candidates: $total"
xargs -P 6 -I{} bash -c 'one {}' < /tmp/alldates.txt
echo "DONE. files: $(ls "$OUT" | wc -l | tr -d ' ')"
