#!/usr/bin/env bash
# Source this before any flash command:  source bin/env.sh
#
# Two things bite on a fresh macOS box; both are documented in FRICTION.md.
#
# 1. The `flash` CLI is installed as a uv tool, which puts it in ~/.local/bin.
# 2. uv's managed CPython ships no CA bundle — its compiled-in default points at
#    a python.org path that does not exist, so every TLS call to api.runpod.io
#    fails with CERTIFICATE_VERIFY_FAILED. flash surfaces that as a *worker*
#    HTTP 500, which sends you debugging the wrong machine. certifi is already
#    installed alongside flash; we just have to point OpenSSL at it.

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
