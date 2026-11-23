"""Shows truthprobe from the latest opencode answers (Windows/Linux database).

Message parts in this core version live inside session_message.data.content,
so that is exactly what we read.
"""
import json
import os
import sqlite3
import sys

base = os.path.join(os.path.expanduser("~"), ".local", "share", "opencode")
candidates = sys.argv[1:] or [
    os.path.join(base, "opencode-feat-truthprobe.db"),
    os.path.join(base, "opencode.db"),
    os.path.join(base, "opencode-local.db"),
]

found = False
for db in candidates:
    if not os.path.exists(db):
        continue
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select id, session_id, data from session_message where type='assistant' order by rowid desc limit 20"
        ).fetchall()
    except sqlite3.Error as error:
        print("error:", db, error)
        continue
    for message_id, session, data in rows:
        payload = json.loads(data)
        content = payload.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            probe = part.get("truthprobe") if isinstance(part, dict) else None
            if not probe:
                continue
            found = True
            print(f"== {os.path.basename(db)} · {session} · {message_id}")
            print(f"   text: {part.get('text', '')[:80]}")
            print(f"   status={probe.get('status')} score={probe.get('score'):.3f} risk={probe.get('risk'):.3f} flagged={probe.get('flagged')}")
            first = probe.get("first") or {}
            print(f"   first: token={first.get('token')!r} score={first.get('score'):.3f}")
            for sentence in probe.get("sentences", []):
                mark = "FLAG" if sentence.get("flag") else "ok  "
                print(f"     {mark} #{sentence['i']} {sentence['score']:.3f}  {sentence['text'][:64]}")
            print()

if not found:
    print("no truthprobe metadata found (run with OPENCODE_TRUTHPROBE=1 and a logprobs-capable model)")
