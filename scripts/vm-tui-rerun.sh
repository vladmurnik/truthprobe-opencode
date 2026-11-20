set -u
mkdir -p /tmp/mock
rm -f /tmp/mock/server.log /tmp/tui-probe.log
pkill -f mock-openai-logprobs.py 2>/dev/null
sleep 1
nohup python3 /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/mock-openai-logprobs.py 8899 >/tmp/mock/server.log 2>&1 &
sleep 2
python3 /tmp/mock/tui-probe.py --out /tmp/tui-probe.log
echo "--- screen (last) ---"
python3 /tmp/mock/screen-dump.py /tmp/tui-probe.log --screens 1
