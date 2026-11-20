set -u
tr -d '\015' < /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/screen-dump.py > /tmp/mock/screen-dump.py
python3 -m py_compile /tmp/mock/screen-dump.py && echo "compile ok"
echo "--- last screen ---"
python3 /tmp/mock/screen-dump.py /tmp/tui-probe.log --screens 2
echo "--- grep confidence ---"
python3 /tmp/mock/screen-dump.py /tmp/tui-probe.log --screens 30 --grep confidence
