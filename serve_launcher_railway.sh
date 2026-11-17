#!/bin/bash
# Railway entrypoint for the Dialectica serve.
# Writes the Dialectica credentials from Railway env vars (never committed
# to this repo) into ~/.dialectica/, then runs the serve loop.
# Env vars set on the Railway service:
#   DIALECTICA_SESSION_TOKEN — contents of ~/.dialectica/session
#   DIALECTICA_AGENT_JSON    — contents of ~/.dialectica/agent.json
#   HMS_API_KEY              — 100milionseek API key (used by hms_provider_env.py)
set -u
set -o pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DIALECTICA_SKILL_ROOT="$ROOT/skill/dialectica"
export DIALECTICA_PROVIDER_CMD="python3 $ROOT/hms_provider_env.py"
TRUED="$DIALECTICA_SKILL_ROOT/scripts/trued.py"
LOG="$ROOT/serve.log"
MAX_QUICK_FAILS=10
quick_fails=0

mkdir -p "$HOME/.dialectica"
chmod 700 "$HOME/.dialectica" 2>/dev/null || true
if [ -n "${DIALECTICA_SESSION_TOKEN:-}" ]; then
    printf '%s' "$DIALECTICA_SESSION_TOKEN" > "$HOME/.dialectica/session"
    chmod 600 "$HOME/.dialectica/session"
fi
if [ -n "${DIALECTICA_AGENT_JSON:-}" ]; then
    printf '%s' "$DIALECTICA_AGENT_JSON" > "$HOME/.dialectica/agent.json"
    chmod 600 "$HOME/.dialectica/agent.json"
fi

echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') launcher: starting serve loop" >> "$LOG"

while true; do
    start_ts=$(date +%s)
    # Tee to stdout too: Railway captures container stdout as deployment logs,
    # so the serve's activity stays visible without SSH-ing into the container.
    python3 "$TRUED" serve 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    end_ts=$(date +%s)
    run_secs=$((end_ts - start_ts))
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') launcher: serve exited rc=$rc after ${run_secs}s" >> "$LOG"
    if [ "$run_secs" -ge 60 ]; then
        quick_fails=0
    else
        quick_fails=$((quick_fails + 1))
    fi
    if [ "$quick_fails" -ge "$MAX_QUICK_FAILS" ]; then
        echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') launcher: $quick_fails quick failures in a row, giving up" >> "$LOG"
        exit 1
    fi
    sleep 15
done
