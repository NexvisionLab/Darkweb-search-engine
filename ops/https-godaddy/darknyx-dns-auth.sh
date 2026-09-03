#!/bin/bash
# certbot --manual-auth-hook: sets the ACME DNS-01 TXT record via GoDaddy's
# API automatically, so certbot never has to pause and wait for a human to
# edit DNS by hand - that manual pause is what kept failing (the terminal
# session kept running straight through it before DNS was actually updated).
set -e

set -a
source /opt/darknyx/.env
set +a

DOMAIN_ROOT="darknyx.com"
if [ "$CERTBOT_DOMAIN" = "$DOMAIN_ROOT" ]; then
    RECORD_NAME="_acme-challenge"
else
    SUBDOMAIN="${CERTBOT_DOMAIN%.$DOMAIN_ROOT}"
    RECORD_NAME="_acme-challenge.$SUBDOMAIN"
fi

HTTP_STATUS=$(curl -s -o /tmp/godaddy-dns-response.json -w "%{http_code}" \
    -X PUT "https://api.godaddy.com/v1/domains/${DOMAIN_ROOT}/records/TXT/${RECORD_NAME}" \
    -H "Authorization: Bearer ${GODADDY_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "[{\"data\": \"${CERTBOT_VALIDATION}\", \"ttl\": 600}]")

if [ "$HTTP_STATUS" -ge 300 ]; then
    echo "GoDaddy DNS update failed (HTTP $HTTP_STATUS):" >&2
    cat /tmp/godaddy-dns-response.json >&2
    exit 1
fi

echo "Set TXT ${RECORD_NAME}.${DOMAIN_ROOT} = ${CERTBOT_VALIDATION}"
echo "Waiting for DNS propagation..."
sleep 45
