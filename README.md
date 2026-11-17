# Dialectica Expert serve (Railway)

Runs the Dialectica Expert `serve` loop on Railway so VM restarts on the
dev machine can no longer kill it.

- `skill/dialectica/scripts/trued.py` — the Dialectica CLI (stdlib only).
- `hms_provider_env.py` — 100milionseek provider; key from `HMS_API_KEY`.
- `serve_launcher_railway.sh` — start command: writes credentials from env
  vars into `~/.dialectica/`, then loops `trued.py serve`.

## Required env vars (set on the Railway service, never in this repo)

- `HMS_API_KEY` — 100milionseek API key.
- `DIALECTICA_SESSION_TOKEN` — contents of `~/.dialectica/session`.
- `DIALECTICA_AGENT_JSON` — contents of `~/.dialectica/agent.json`.

## Start command

```sh
bash serve_launcher_railway.sh
```
