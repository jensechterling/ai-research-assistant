"""Probe Melious API behaviour for deepseek-v4.1-flash (task 1.1 of api-pipeline).

Usage: uv run python scripts/probe_melious.py

Reads the key from MELIOUS_API_KEY or the Keychain item "melious-api-key".
Never prints the key. Makes ~10 small requests (well under EUR 0.01).
"""
import json
import os
import subprocess
import sys
import time

import httpx

BASE_URL = "https://api.melious.ai/v1"
MODEL = "deepseek-v4.1-flash"

ARTICLE = (
    "Title: Small teams ship faster\n\n"
    "A study of 40 software teams found that teams of 3-5 engineers shipped features "
    "30% faster than teams of 8 or more, mainly because they spent less time in "
    "coordination meetings. The authors recommend splitting large teams by product area."
)
PROFILE = "Work: product lead at a software company. Personal: fitness, PKM."
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "kb_folder": {"type": "string"},
    },
    "required": ["summary", "key_findings", "tags", "kb_folder"],
    "additionalProperties": False,
}
SYSTEM = (
    "You analyse articles for a reader. Reply with a single JSON object only, matching this "
    f"JSON schema:\n{json.dumps(SCHEMA)}\nReader profile:\n{PROFILE}\n"
    "Knowledge-base folders: Leadership, Product, AI & ML, Misc"
)


def get_key() -> str:
    key = os.environ.get("MELIOUS_API_KEY")
    if key:
        return key
    out = subprocess.run(
        ["security", "find-generic-password", "-s", "melious-api-key", "-w"],
        capture_output=True, text=True, timeout=10,
    )
    if out.returncode != 0:
        sys.exit("No key: set MELIOUS_API_KEY or add Keychain item melious-api-key")
    return out.stdout.strip()


def call(client: httpx.Client, label: str, body: dict, key: str | None = None) -> dict | None:
    headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": ARTICLE},
    ]} | body
    start = time.monotonic()
    try:
        r = client.post("/chat/completions", json=payload, headers=headers)
    except httpx.HTTPError as e:
        print(f"\n### {label}\nTRANSPORT ERROR: {type(e).__name__}: {e}")
        return None
    elapsed = time.monotonic() - start
    print(f"\n### {label}\nHTTP {r.status_code} in {elapsed:.1f}s")
    try:
        data = r.json()
    except ValueError:
        print("non-JSON body:", r.text[:400])
        return None
    if r.status_code != 200:
        print("error body:", json.dumps(data)[:600])
        return data
    choice = data["choices"][0]
    msg = choice["message"]
    content = msg.get("content") or ""
    print("finish_reason:", choice.get("finish_reason"))
    print("usage:", json.dumps(data.get("usage")))
    extra = {k: v for k, v in data.items() if k not in ("choices", "usage", "id", "object", "created", "model")}
    print("extra top-level fields:", json.dumps(extra)[:600])
    print("message keys:", sorted(msg.keys()))
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    print(f"reasoning chars: {len(reasoning)}")
    print("content (first 300):", content[:300].replace("\n", " "))
    try:
        parsed = json.loads(content)
        print("content parses as JSON:", True, "| keys:", sorted(parsed.keys()))
    except (ValueError, AttributeError):
        print("content parses as JSON:", False)
    return data


def main() -> None:
    key = get_key()
    with httpx.Client(base_url=BASE_URL, timeout=180) as client:
        auth = {"Authorization": f"Bearer {key}"}
        client.headers.update(auth)

        call(client, "A. json_object mode", {"response_format": {"type": "json_object"}, "max_tokens": 4000})
        call(client, "B. json_schema strict", {
            "response_format": {"type": "json_schema", "json_schema": {"name": "analysis", "strict": True, "schema": SCHEMA}},
            "max_tokens": 4000,
        })
        call(client, "C. no response_format", {"max_tokens": 4000})
        call(client, "D1. reasoning_effort=none", {"response_format": {"type": "json_object"}, "max_tokens": 4000, "reasoning_effort": "none"})
        call(client, "D2. thinking disabled (DeepSeek style)", {"response_format": {"type": "json_object"}, "max_tokens": 4000, "thinking": {"type": "disabled"}})
        call(client, "D3. reasoning.enabled=false", {"response_format": {"type": "json_object"}, "max_tokens": 4000, "reasoning": {"enabled": False}})
        call(client, "E. max_tokens=60 (truncation)", {"response_format": {"type": "json_object"}, "max_tokens": 60})
        call(client, "F. unknown model", {"model": "deepseek-does-not-exist", "max_tokens": 20})

        client.headers.pop("Authorization")
        call(client, "G. invalid key", {"max_tokens": 20}, key="invalid-key-for-probe")


if __name__ == "__main__":
    main()
