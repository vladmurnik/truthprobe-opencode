set -u
mkdir -p /tmp/mock
pkill -f mock-openai-logprobs.py 2>/dev/null
sleep 1
nohup python3 /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/mock-openai-logprobs.py 8899 >/tmp/mock/server.log 2>&1 &
sleep 2
export HOME_TEST=/home/adik
cd /home/adik/src/opencode/packages/cli
OPENCODE_TRUTHPROBE=1 \
OPENCODE_CONFIG=/mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/mock-opencode.json \
./dist/cli-linux-x64/bin/opencode run --model mock/mock-1 "What is the capital of France? Answer in two sentences." 2>&1 | tail -5
echo "--- latest part truthprobe ---"
python3 - <<'PY'
import json, os, sqlite3, glob
for p in glob.glob(os.path.expanduser("~/.local/share/opencode/*.db")):
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        rows = con.execute("select data from session_part where type='text' order by time_created desc limit 1").fetchall()
    except Exception as exc:
        print(p, "err", exc); continue
    for (data,) in rows:
        d = json.loads(data)
        tp = d.get("truthprobe")
        print("binary artifact part:", (d.get("text") or "")[:60], "| truthprobe:", "YES" if tp else "no")
        if tp:
            print(json.dumps(tp)[:200])
PY
