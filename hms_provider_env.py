#!/usr/bin/env python3
"""Dialectica provider wrapper: 100milionseek free gateway path (Railway build).

Reads a prompt on stdin, sends it to the 100milionseek OpenAI-compatible
API (model deepseek-v4.1-flash-free, 198K context), writes ONLY the answer
to stdout (no logs, no extra text — trued.py pipes stdout as the Answer).

Railway variant: the API key comes from the HMS_API_KEY env var (set on the
Railway service, never committed). The local build (hms_provider.py) uses
the Muse vault surrogate instead; the logic is otherwise identical.

Why this exists: Dialectica's server-rendered job bodies run ~9k-71k
tokens, but Groq's free tier caps at 8,000 TPM, so every job dropped
with HTTP 413 and each drop cost reliability (REL-005 slashes). This
gateway takes 62k-token prompts (verified 2026-11-17) with a 400M
tokens/day allowance — far above the ~5 answers/day the Expert takes.

Model: deepseek-v4.1-flash-free (override with DIALECTICA_HMS_MODEL).
API key: the registered custom.100milionseek connection (surrogate swap
via dynamic_credentials, as hms_chat.py does) — never in a file.
Retry backoff for 429/5xx: 20s, 45s, then fail. Empty responses are
retried the same way (fix 2026-11-17: two jobs dropped on empty text).
Python stdlib only. Talks only to 100milionseek.top. No redirects.
Note: no web-search grounding on this path; the model answers from its
own knowledge, same as the Groq path it replaces.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("DIALECTICA_HMS_MODEL", "deepseek-v4.1-flash-free")
BASE = "https://100milionseek.top/v1"
BACKOFFS = (20, 45)
REQUEST_TIMEOUT_S = 240
ENDPOINT = "/chat/completions"
# Cloudflare 1010 blocks the default Python UA; send a browser UA.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call_once(prompt):
    """Stream the completion (stream: true) and accumulate the answer.

    The gateway sits behind Cloudflare with a 120s Proxy Read Timeout:
    a non-streaming call that takes longer (big prompt + long answer)
    dies with HTTP 524. Streaming keeps data flowing, so the proxy
    does not time the request out.
    """
    api_key = os.environ.get("HMS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("HMS_API_KEY env var is not set")
    req = urllib.request.Request(BASE + ENDPOINT)
    req.add_header("Authorization", "Bearer " + api_key)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "text/event-stream")
    req.add_header("Content-Type", "application/json")
    data = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "stream": True,
    }).encode("utf-8")
    parts = []
    with urllib.request.build_opener(_NoRedirect()).open(
            req, data=data, timeout=REQUEST_TIMEOUT_S) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload_s = line[5:].strip()
            if payload_s == "[DONE]":
                break
            try:
                chunk = json.loads(payload_s)
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    parts.append(delta["content"])
    return "".join(parts)


def main():
    prompt = sys.stdin.read()
    if not prompt.strip():
        print("empty prompt", file=sys.stderr)
        return 2

    last_err = None
    answer = None
    for attempt in range(len(BACKOFFS) + 1):
        try:
            answer = call_once(prompt)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503) and attempt < len(BACKOFFS):
                time.sleep(BACKOFFS[attempt])
                continue
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                detail = ""
            print(f"100milionseek API error: HTTP {e.code} {detail}",
                  file=sys.stderr)
            return 1
        except Exception as e:
            last_err = str(e)
            if attempt < len(BACKOFFS):
                time.sleep(BACKOFFS[attempt])
                continue
            print(f"100milionseek API network error: {e}", file=sys.stderr)
            return 1
        # Call succeeded: an empty stream is a transient gateway hiccup
        # (dropped jobs 90043871 + 56aeeb39 on 2026-11-17) — retry instead
        # of dropping the job immediately.
        if answer is not None and answer.strip():
            break
        last_err = "empty response (no text)"
        answer = None
        if attempt < len(BACKOFFS):
            time.sleep(BACKOFFS[attempt])
            continue
    if answer is None:
        print(f"100milionseek API failed after retries: {last_err}",
              file=sys.stderr)
        return 1

    answer = answer.strip()
    if not answer:
        print("100milionseek returned no text", file=sys.stderr)
        return 1
    sys.stdout.write(answer)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
