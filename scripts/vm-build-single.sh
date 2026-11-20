set -u
export PATH=$HOME/.bun/bin:$PATH
cd /home/adik/src/opencode/packages/cli
export OPENCODE_TARGET=linux-x64
export OPENCODE_RELEASE=1
time bun run script/build.ts --single --skip-install --skip-web-ui 2>&1 | tail -40
echo "=== artifact ==="
ls -la dist/ 2>/dev/null | head
find dist -maxdepth 3 -name opencode -type f 2>/dev/null | head -5 | while read -r f; do ls -lh "$f"; done
