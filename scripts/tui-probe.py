#!/usr/bin/env python3
"""T9 probe: render the truthprobe badge/block in the real TUI via a pty.

Spawns the opencode TUI (Solid) inside a pseudo-terminal, types one prompt,
waits for the answer, then kills the process and prints the sanitized screen
lines that mention confidence / doubtful sentences.

Usage:
  python3 tui-probe.py [--repo /home/adik/src/opencode] [--wait 45] [--out /tmp/tui-probe.log]
"""

import argparse
import os
import pty
import re
import select
import signal
import sys
import time

ANSI = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][A-B0-9]")


def sanitize(raw: bytes) -> str:
    text = ANSI.sub(b"", raw).decode("utf-8", "replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/home/adik/src/opencode")
    ap.add_argument("--config", default="/mnt/c/Users/adik/Desktop/progects/opencode-truthprobe/scripts/mock-opencode.json")
    ap.add_argument("--prompt", default="What is the capital of France and how many people live there?")
    ap.add_argument("--startup", type=float, default=18.0, help="seconds to wait for TUI boot")
    ap.add_argument("--wait", type=float, default=45.0, help="seconds to wait for the answer")
    ap.add_argument("--out", default="/tmp/tui-probe.log")
    args = ap.parse_args()

    inner = (
        f"cd {args.repo} && export PATH=$HOME/.bun/bin:$PATH && "
        f"OPENCODE_TRUTHPROBE=1 OPENCODE_CONFIG={args.config} "
        f"exec /home/adik/.bun/bin/bun run --cwd packages/cli src/index.ts"
    )

    pid, fd = pty.fork()
    if pid == 0:  # child
        os.execvp("/bin/bash", ["bash", "-lc", inner])
        os._exit(127)

    chunks = []

    def pump(seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.4)
            if not r:
                continue
            try:
                data = os.read(fd, 65536)
            except OSError:
                return
            if not data:
                return
            chunks.append(data)

    rc = 0
    try:
        pump(args.startup)
        os.write(fd, (args.prompt + "\r").encode())
        pump(args.wait)
    finally:
        for sig in (signal.SIGINT, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except OSError:
                break
            pump(1.0)
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            _, status = os.waitpid(pid, 0)
            rc = status
        except OSError:
            pass

    raw = b"".join(chunks)
    with open(args.out, "wb") as fh:
        fh.write(raw)

    text = sanitize(raw)
    keep = ("confidence", "doubtful", "truthprobe", "Paris", "million", "unavailable")
    hits = [line for line in text.split("\n") if any(k.lower() in line.lower() for k in keep)]

    print(f"captured bytes={len(raw)} lines={len(text.split(chr(10)))} hits={len(hits)}")
    for line in hits[:60]:
        print("  |", line.strip()[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
