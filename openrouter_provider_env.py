#!/usr/bin/env python3
"""Dialectica provider wrapper: OpenRouter free-model path (Railway build).

Reads a prompt on stdin, sends it to the OpenRouter OpenAI-compatible API
(free :free model, 256K-1M context), writes ONLY the answer to stdout
(no logs, no extra text — trued.py pipes stdout as the Answer).

Railway variant: the API key comes from the OPENROUTER_API_KEY env var (set
on the Railway service, never committed). The local build uses the Muse
vault surrogate via dynamic_credentials when no env key is present.

Why this exists: Dialectica's server-rendered job bodies run ~9k-71k
tokens, but Groq's free tier caps at 8,000 TPM (HTTP 413 drops), and the
100milionseek DeepSeek path is slow and sometimes returns empty text,
which cost REL-005 suspension slashes. OpenRouter free models offer
256K+ context with no per-minute token cap advertised, at 50 req/day.

Model: google/gemma-4-31b-it:free by default (262K context, override with
DIALECTICA_OR_MODEL). Free tier: 50 requests/day — the Expert takes at
most 20 answers/day, so retries must stay rare.
Retry backoff for 429/5xx: 20s, 45s, then fail. Empty responses are
retried the same way (same fix as the 100milionseek provider).
Python stdlib only. Talks only to openrouter.ai. No redirects.
Note: no web-search grounding on this path; the model answers from its
own knowledge, same as the other free paths.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("DIALECTICA_OR_MODEL", "nvidia/nemotron-3.5-lightning:free")
BASE = "https://openrouter.ai/api/v1"
BACKOFFS = (20, 45)
REQUEST_TIMEOUT_S = 240
ENDPOINT = "/chat/completions"
# OpenRouter docs ask for a descriptive User-Agent / HTTP-Referer.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
# Dialectica answers run 10K-27K chars (~3K-7K tokens); cap high so a
# long answer is not cut mid-sentence. Free endpoints may clamp this.
MAX_TOKENS = int(os.environ.get("DIALECTICA_OR_MAX_TOKENS", "16384"))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def _api_key():
    """Real key from env (Railway), else the Muse vault surrogate (local)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
        from dynamic_credentials import add_surrogate_to_request  # noqa: F401
        from dynamic_credentials import dynamic_credential_entry
        entry = dynamic_credential_entry("custom.openrouter")
        surrogate = str(entry.get("surrogate", "")).strip()
        if surrogate.startswith("hsurr:"):
            return surrogate
    except Exception:
        pass
    return ""


def call_once(prompt):
    """Stream the completion (stream: true) and accumulate the answer.

    Streaming keeps data flowing so no proxy read timeout kills a long
    generation, the same reason the 100milionseek provider streams.
    Returns (answer_text, usage_dict_or_None).
    """
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY env var is not set")
    req = urllib.request.Request(BASE + ENDPOINT)
    req.add_header("Authorization", "Bearer " + api_key)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("HTTP-Referer", "https://muse.local/dialectica")
    req.add_header("X-Title", "Muse Dialectica Expert")
    req.add_header("Accept", "text/event-stream")
    req.add_header("Content-Type", "application/json")
    data = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode("utf-8")
    parts = []
    usage = None
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
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    parts.append(delta["content"])
    return "".join(parts), usage


def main():
    prompt = sys.stdin.read()
    if not prompt.strip():
        print("empty prompt", file=sys.stderr)
        return 2

    last_err = None
    answer = None
    usage = None
    for attempt in range(len(BACKOFFS) + 1):
        try:
            answer, usage = call_once(prompt)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503) and attempt < len(BACKOFFS):
                time.sleep(BACKOFFS[attempt])
                continue
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                detail = ""
            print(f"OpenRouter API error: HTTP {e.code} {detail}",
                  file=sys.stderr)
            return 1
        except Exception as e:
            last_err = str(e)
            if attempt < len(BACKOFFS):
                time.sleep(BACKOFFS[attempt])
                continue
            print(f"OpenRouter API network error: {e}", file=sys.stderr)
            return 1
        # Call succeeded: an empty stream is a transient gateway hiccup —
        # retry instead of dropping the job immediately.
        if answer is not None and answer.strip():
            break
        last_err = "empty response (no text)"
        answer = None
        usage = None
        if attempt < len(BACKOFFS):
            time.sleep(BACKOFFS[attempt])
            continue
    if answer is None:
        print(f"OpenRouter API failed after retries: {last_err}",
              file=sys.stderr)
        return 1

    answer = answer.strip()
    if not answer:
        print("OpenRouter returned no text", file=sys.stderr)
        return 1
    if usage:
        print(f"openrouter usage: {json.dumps(usage)}", file=sys.stderr)
    sys.stdout.write(answer)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
