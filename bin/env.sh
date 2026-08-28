#!/usr/bin/env bash

export PATH="$HOME/.local/bin:$PATH"

FLASH_PY="$HOME/.local/share/uv/tools/runpod-flash/bin/python"
if [ -x "$FLASH_PY" ]; then
  CA="$("$FLASH_PY" -c 'import certifi; print(certifi.where())' 2>/dev/null)"
  if [ -n "$CA" ] && [ -f "$CA" ]; then
    export SSL_CERT_FILE="$CA"
    export REQUESTS_CA_BUNDLE="$CA"
  fi
fi

# RUNPOD_API_KEY from .env (gitignored). Note: a set RUNPOD_API_KEY overrides the
# `flash login` token, and a stale key fails *silently* — flash still prints its
# healthy ready line while provisioning logs a 401.
if [ -f "$(dirname "${BASH_SOURCE[0]:-$0}")/../.env" ]; then
  set -a
  . "$(dirname "${BASH_SOURCE[0]:-$0}")/../.env"
  set +a
fi
