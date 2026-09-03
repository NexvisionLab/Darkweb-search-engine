#!/bin/bash
set -e
GW=$(ip route show | awk '/^default via.*dev ens33/ {print $3; exit}')
DEV=ens33
if [ -z "$GW" ]; then
  logger -t darkweb-aws-bypass "no ens33 default gateway found, aborting"
  exit 1
fi
TMPJSON=$(mktemp)
TMPLIST=$(mktemp)
curl -fsS -m 30 https://ip-ranges.amazonaws.com/ip-ranges.json -o "$TMPJSON"
python3 -c "
import json
data = json.load(open('$TMPJSON'))
cf = sorted(set(p['ip_prefix'] for p in data['prefixes'] if p['service'] == 'CLOUDFRONT'))
open('$TMPLIST', 'w').write('\n'.join(cf) + '\n')
"
count=0
while read -r cidr; do
  ip route replace "$cidr" via "$GW" dev "$DEV" && count=$((count+1))
done < "$TMPLIST"
logger -t darkweb-aws-bypass "applied $count CloudFront route bypasses via $DEV (gw $GW)"
rm -f "$TMPJSON" "$TMPLIST"
