set -u
export PATH=$HOME/.bun/bin:$PATH
cd /home/adik/src/opencode
tr -d '\015' < /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/patches/apply-tui-store.py > /tmp/apply-tui-store.py
python3 /tmp/apply-tui-store.py || exit 1
grep -n "truthprobe" packages/client/src/solid/data.ts
bun run --cwd packages/client typecheck 2>&1 | tail -5
bun run --cwd packages/tui typecheck 2>&1 | tail -5
