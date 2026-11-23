#!/usr/bin/env python3
"""How many built-in opencode models live on each API protocol (matters for logprobs)."""
import collections
import json

PATH = "/home/adik/src/opencode/packages/core/src/models-dev/snapshot.txt"
data = json.load(open(PATH, encoding="utf-8"))
models = data["opencode"]["models"]

by_api = collections.Counter()
for mid, m in models.items():
    for api in (m.get("api") or {}):
        by_api[api] += 1

print("opencode models:", len(models))
for api, n in by_api.most_common():
    print(f"  {api:20s} {n}")

# chat-completions — the only family where logprobs apply at all
cc = [mid for mid, m in models.items() if "chat-completions" in (m.get("api") or {})]
print("\nchat-completions models:", len(cc))
for mid in sorted(cc):
    m = models[mid]
    api = m["api"]["chat-completions"]
    base = (api.get("base_url") or "").replace("https://opencode.ai/inference", "")
    temp = ((m.get("capabilities") or {}).get("temperature") or {}).get("supported")
    print(f"  {mid:42s} {base:28s} temp={temp}")
