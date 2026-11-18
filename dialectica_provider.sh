#!/bin/bash
# Provider dispatcher for the Dialectica serve (Railway).
# Contract (same as DIALECTICA_PROVIDER_CMD): read the prompt on stdin,
# write ONLY the answer to stdout (diagnostics go to stderr).
#
# Tries OpenRouter first (free model, nvidia/nemotron-3.5-lightning:free)
# when OPENROUTER_API_KEY is set on the service; falls back to the proven
# 100milionseek path (hms_provider_env.py) when the key is unset or the
# OpenRouter call fails. HMS_API_KEY stays set on the service as the
# fallback and is never removed. The OpenRouter attempt is capped at 600s
# so the fallback still fits inside trued.py's 900s provider timeout.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT="$(mktemp)"
trap 'rm -f "$PROMPT"' EXIT
cat > "$PROMPT"
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
    if timeout 600 python3 "$ROOT/openrouter_provider_env.py" < "$PROMPT"; then
        exit 0
    fi
    echo "dialectica_provider: OpenRouter failed, falling back to 100milionseek" >&2
fi
python3 "$ROOT/hms_provider_env.py" < "$PROMPT"
