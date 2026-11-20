#!/usr/bin/env python3
"""Reconstruct the final visible screen from a raw pty capture of the opencode TUI.

Minimal VT100/ANSI screen model: prints, CR/LF, BS, CSI H/f (cursor position),
A/B/C/D (relative moves), J/K (erase), E/F, and ignores SGR/private modes.
Prints the last N non-empty screens (screens are separated by clear+home).

Usage: python3 screen-dump.py /tmp/tui-probe.log [--rows 50 --cols 200 --screens 3]
"""

import argparse
import re
import sys

CSI = re.compile(r"\x1b\[([0-9;?]*)([@-~])")


class Screen:
    def __init__(self, rows: int, cols: int) -> None:
        self.rows, self.cols = rows, cols
        self.grid = [[" "] * cols for _ in range(rows)]
        self.r = self.c = 0
        self.snapshots = []

    def snapshot(self) -> str:
        lines = ["".join(row).rstrip() for row in self.grid]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def put(self, ch: str) -> None:
        if ch == "\n":
            self.r = min(self.r + 1, self.rows - 1)
            return
        if ch == "\r":
            self.c = 0
            return
        if ch == "\b":
            self.c = max(self.c - 1, 0)
            return
        if self.c >= self.cols:
            self.c = 0
            self.r = min(self.r + 1, self.rows - 1)
        self.grid[self.r][self.c] = ch
        self.c += 1

    def csi(self, params: str, final: str) -> None:
        private = params.startswith("?") or params.startswith(">")
        nums = [int(p) for p in params.lstrip("?>").split(";") if p.isdigit()] if params.lstrip("?>") else []
        n = nums[0] if nums else 1
        if final in "Hf" and not private:
            row = (nums[0] if len(nums) > 0 else 1) or 1
            col = (nums[1] if len(nums) > 1 else 1) or 1
            self.r = min(max(row - 1, 0), self.rows - 1)
            self.c = min(max(col - 1, 0), self.cols - 1)
        elif final == "A":
            self.r = max(self.r - n, 0)
        elif final == "B":
            self.r = min(self.r + n, self.rows - 1)
        elif final == "C":
            self.c = min(self.c + n, self.cols - 1)
        elif final == "D":
            self.c = max(self.c - n, 0)
        elif final == "G":
            self.c = min(max(n - 1, 0), self.cols - 1)
        elif final == "d":
            self.r = min(max(n - 1, 0), self.rows - 1)
        elif final == "K":
            mode = nums[0] if nums else 0
            if mode == 0:
                for i in range(self.c, self.cols):
                    self.grid[self.r][i] = " "
            elif mode == 1:
                for i in range(0, self.c + 1):
                    self.grid[self.r][i] = " "
            else:
                self.grid[self.r] = [" "] * self.cols
        elif final == "J":
            mode = nums[0] if nums else 0
            if mode in (2, 3):
                self.snapshots.append(self.snapshot())
                self.grid = [[" "] * self.cols for _ in range(self.rows)]
                self.r = self.c = 0
            elif mode == 0:
                for i in range(self.c, self.cols):
                    self.grid[self.r][i] = " "
                for row in range(self.r + 1, self.rows):
                    self.grid[row] = [" "] * self.cols

    def feed(self, data: str) -> None:
        i = 0
        while i < len(data):
            ch = data[i]
            if ch == "\x1b":
                m = CSI.match(data, i)
                if m:
                    self.csi(m.group(1), m.group(2))
                    i = m.end()
                    continue
                # skip OSC / other escape sequences up to a terminator
                if i + 1 < len(data) and data[i + 1] in "]P^_":
                    end = data.find("\x07", i)
                    st = data.find("\x1b\\", i)
                    cands = [p for p in (end, st) if p != -1]
                    if not cands:
                        return
                    pos = min(cands)
                    i = pos + (2 if pos == st else 1)
                    continue
                i += 2
                continue
            if ch < " " or ch == "\x7f":
                self.put(ch)
                i += 1
                continue
            self.put(ch)
            i += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--rows", type=int, default=55)
    ap.add_argument("--cols", type=int, default=200)
    ap.add_argument("--screens", type=int, default=3)
    ap.add_argument("--grep", default=None)
    args = ap.parse_args()

    raw = open(args.path, "rb").read().decode("utf-8", "replace")
    scr = Screen(args.rows, args.cols)
    scr.feed(raw)
    scr.snapshots.append(scr.snapshot())
    shots = [s for s in scr.snapshots if s.strip()]
    for n, s in enumerate(shots[-args.screens :], 1):
        print(f"===== screen {n}/{min(len(shots), args.screens)} =====")
        for line in s.split("\n"):
            if args.grep and args.grep.lower() not in line.lower():
                continue
            print(line)
    print(f"===== total screens={len(shots)} grep={args.grep} =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
