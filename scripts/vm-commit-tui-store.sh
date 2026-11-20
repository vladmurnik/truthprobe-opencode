set -u
export PATH=$HOME/.bun/bin:$PATH
cd /home/adik/src/opencode
git add -A
git -c user.name="adik" -c user.email="adik@local" commit -q -m "fix(tui): apply truthprobe metadata from session.text.ended events

The solid client store only copied event.data.text into the in-memory
assistant text part, so the live TUI never saw the durable truthprobe
payload until a full session refetch. Copy it through." && echo "committed"
git log --oneline -3
git diff --stat 007afb1 HEAD | tail -3
git format-patch 007afb1 --stdout > /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/patches/truthprobe-0001.patch
wc -l /mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/patches/truthprobe-0001.patch
