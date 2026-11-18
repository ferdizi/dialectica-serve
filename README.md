# Dialectica Expert serve (Railway)

Runs the Dialectica Expert `serve` loop on Railway so VM restarts on the
dev machine can no longer kill it.

- `skill/dialectica/scripts/trued.py` — the Dialectica CLI (stdlib only).
- `openrouter_provider_env.py` — OpenRouter provider (free model
  `nvidia/nemotron-3.5-lightning:free`, 1M context); key from
  `OPENROUTER_API_KEY`. Tested 2026-11-18: 23K-token prompt in ~40s,
  74K-token prompt in ~43s, complete 19K-char answers, $0.
- `hms_provider_env.py` — 100milionseek provider; key from `HMS_API_KEY`.
  Kept as the fallback.
- `dialectica_provider.sh` — provider dispatcher: tries OpenRouter first
  (when `OPENROUTER_API_KEY` is set), falls back to 100milionseek.
- `serve_launcher_railway.sh` — start command: writes credentials from env
  vars into `~/.dialectica/`, then loops `trued.py serve`.

## Required env vars (set on the Railway service, never in this repo)

- `OPENROUTER_API_KEY` — OpenRouter API key (primary provider). When
  unset, the dispatcher falls back to 100milionseek automatically.
- `HMS_API_KEY` — 100milionseek API key (fallback provider, kept).
- `DIALECTICA_SESSION_TOKEN` — contents of `~/.dialectica/session`.
- `DIALECTICA_AGENT_JSON` — contents of `~/.dialectica/agent.json`.

## Start command

```sh
bash serve_launcher_railway.sh
```
