set -u
echo "--- requests seen by mock ---"
tail -n 3 /tmp/mock/requests.jsonl 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
    except Exception:
        print('unparsed:', line[:200]); continue
    body = d.get('body') or d.get('request') or d
    print({k: body.get(k) for k in ('model','logprobs','top_logprobs','stream','max_tokens')} if isinstance(body, dict) else str(body)[:200])
"
echo "--- parts with truthprobe ---"
python3 - <<'PY'
import json, os, sqlite3, glob
paths = glob.glob(os.path.expanduser("~/.local/share/opencode/*.db"))
for p in paths:
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        rows = con.execute("select data from session_part where type='text' order by time_created desc limit 6").fetchall()
    except Exception as exc:
        print(p, "err", exc); continue
    for (data,) in rows:
        try:
            d = json.loads(data)
        except Exception:
            continue
        tp = d.get("truthprobe")
        print(p.split("/")[-1], "text=", (d.get("text") or "")[:60], "| truthprobe=", "YES" if tp else "no", json.dumps(tp)[:160] if tp else "")
PY
