#!/bin/bash
# NSE's corporate-actions feed, pulled in monthly windows across the whole period.
# One handshake for cookies, then a window at a time; the API refuses a wide range.
SP="$(cd "$(dirname "$0")" && pwd)"; OUT="$SP/ca"
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
C=$(mktemp)
curl -s -c "$C" -o /dev/null --max-time 30 -H "User-Agent: $UA" https://www.nseindia.com/
python3 - <<'PY' > /tmp/wins.txt
from datetime import date
d = date(2021,10,1)
while d < date(2026,10,2):
    nxt = date(d.year + (d.month//12), (d.month % 12) + 1, 1)
    end = min(nxt, date(2026,10,2))
    print(f"{d:%d-%m-%Y} {end:%d-%m-%Y} {d:%Y%m}")
    d = nxt
PY
while read -r f t tag; do
  [ -s "$OUT/$tag.json" ] && continue
  curl -s -b "$C" --max-time 60 -H "User-Agent: $UA" \
    -H "Referer: https://www.nseindia.com/companies-listing/corporate-filings-actions" \
    "https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=$f&to_date=$t" \
    -o "$OUT/$tag.json"
  n=$(python3 -c "import json,sys;d=json.load(open('$OUT/$tag.json'));print(len(d if isinstance(d,list) else d.get('data',[])))" 2>/dev/null || echo ERR)
  echo "  $tag  $n"
  sleep 0.4
done < /tmp/wins.txt
echo DONE
