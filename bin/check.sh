#!/usr/bin/env bash
# Verifies the local setup before you burn time on a deploy.
set -u
cd "$(dirname "$0")/.."
source bin/env.sh
echo "flash:        $(command -v flash || echo MISSING)  $(flash --version 2>/dev/null)"
echo "SSL_CERT_FILE: ${SSL_CERT_FILE:-UNSET}"
printf 'API key:      '
code=$(curl -s -o /dev/null -w '%{http_code}' https://rest.runpod.io/v1/endpoints \
  -H "Authorization: Bearer ${RUNPOD_API_KEY:-none}")
[ "$code" = "200" ] && echo "ok (200)" || echo "FAILED ($code)"
