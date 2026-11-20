#!/usr/bin/env python3
"""Разбор встроенного snapshot реестра models.dev внутри opencode."""
import json
import sys

PATH = "/home/adik/src/opencode/packages/core/src/models-dev/snapshot.txt"

raw = open(PATH, encoding="utf-8").read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("NOT JSON, first 120 chars:", repr(raw[:120]))
    sys.exit(0)

print("root type:", type(data).__name__, "keys:", list(data)[:8] if isinstance(data, dict) else len(data))

providers = data.get("providers", data) if isinstance(data, dict) else data
if not isinstance(providers, dict):
    sys.exit(0)

print("providers:", len(providers))
zen_key = None
for key in providers:
    if "opencode" in key.lower():
        zen_key = key
print("opencode-ish provider key:", zen_key)

for key in [zen_key] if zen_key else []:
    p = providers[key]
    print("\n== provider:", key, "==")
    for field in ("name", "api", "npm", "doc"):
        if field in p:
            print(f"  {field}: {p[field]}")
    models = p.get("models", {})
    print("  models:", len(models))
    for mid, m in list(models.items())[:40]:
        caps = m.get("capabilities") or {}
        print(
            f"    - {mid:45s} api={m.get('api') or p.get('api')} "
            f"caps={ {k: v for k, v in caps.items() if k in ('tools','temperature')} }"
            f" limit_out={ (m.get('limit') or {}).get('output') }"
        )
