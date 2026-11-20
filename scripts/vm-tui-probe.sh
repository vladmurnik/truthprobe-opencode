set -u
pkill -f mock-openai-logprobs.py 2>/dev/null
mkdir -p /tmp/mock
nohup python3 /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/mock-openai-logprobs.py 8899 >/tmp/mock/server.log 2>&1 &
sleep 2
curl -s -m 3 http://127.0.0.1:8899/v1/models | head -c 200
echo
tr -d '\015' < /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/tui-probe.py > /tmp/mock/tui-probe.py
python3 -m py_compile /tmp/mock/tui-probe.py && echo "compile ok"
python3 /tmp/mock/tui-probe.py --out /tmp/tui-probe.log
echo "exit=$?"
