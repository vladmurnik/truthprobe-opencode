import json
import os
import sqlite3

base = os.path.join(os.path.expanduser("~"), ".local", "share", "opencode")
for name in ("opencode-feat-truthprobe.db", "opencode.db"):
    db = os.path.join(base, name)
    if not os.path.exists(db):
        continue
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
    print("==", name, "tables:", tables)
    for table in ("session", "session_message", "session_part", "message", "part"):
        if table not in tables:
            continue
        count = con.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"   {table}: {count} rows")
    if "session_part" in tables:
        cols = [r[1] for r in con.execute("pragma table_info(session_part)")]
        print("   session_part cols:", cols)
        for row in con.execute("select * from session_part order by rowid desc limit 2"):
            print("   row:", str(row)[:400])
    if "session" in tables:
        for row in con.execute("select id, time_created from session order by rowid desc limit 3"):
            print("   session:", row)
