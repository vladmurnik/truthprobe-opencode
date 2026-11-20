#!/usr/bin/env python3
"""Сколько встроенных моделей opencode живёт на каждом API-протоколе (важно для logprobs)."""
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

# chat-completions — единственное семейство, где logprobs вообще применимы
cc = [mid for mid, m in models.items() if "chat-completions" in (m.get("api") or {})]
print("\nchat-completions models:", len(cc))
for mid in sorted(cc):
    m = models[mid]
    api = m["api"]["chat-completions"]
    base = (api.get("base_url") or "").replace("https://opencode.ai/inference", "")
    temp = ((m.get("capabilities") or {}).get("temperature") or {}).get("supported")
    print(f"  {mid:42s} {base:28s} temp={temp}")
