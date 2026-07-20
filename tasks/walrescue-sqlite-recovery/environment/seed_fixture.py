"""Build-time-only generator for the development database and WAL."""

import random
import sqlite3
import struct
from pathlib import Path

ROOT = Path("/app/data")
ROOT.mkdir(parents=True, exist_ok=True)
DB = ROOT / "gateway.db"
PAGE = 1024


def cksum(data, state=(0, 0)):
    s0, s1 = state
    for offset in range(0, len(data), 8):
        x0, x1 = struct.unpack_from("<II", data, offset)
        s0 = (s0 + x0 + s1) & 0xFFFFFFFF
        s1 = (s1 + x1 + s0) & 0xFFFFFFFF
    return s0, s1


con = sqlite3.connect(DB)
con.execute(f"PRAGMA page_size={PAGE}")
con.execute("PRAGMA journal_mode=DELETE")
con.execute("VACUUM")
con.execute("CREATE TABLE readings(id INTEGER PRIMARY KEY, source TEXT, value INTEGER)")
con.executemany("INSERT INTO readings VALUES(?,?,?)", [(i, f"rack-{i % 9}", i * 11) for i in range(1, 120)])
con.commit()
base = DB.read_bytes()
con.executemany("UPDATE readings SET value=value+? WHERE id=?", [(7000 + i, i) for i in range(4, 100, 4)])
con.executemany("INSERT INTO readings(source,value) VALUES(?,?)", [(f"new-{i}", 90000 + i) for i in range(40)])
con.commit()
target = DB.read_bytes()
con.close()
DB.write_bytes(base)

salt1, salt2 = 0x71A20B6C, 0x4E9912D3
head = struct.pack(">IIIIII", 0x377F0682, 3007000, PAGE, 0, salt1, salt2)
state = cksum(head)
wal = bytearray(head + struct.pack(">II", *state))
old = [base[i:i+PAGE] for i in range(0, len(base), PAGE)]
new = [target[i:i+PAGE] for i in range(0, len(target), PAGE)]
delta = [(i + 1, page) for i, page in enumerate(new) if i >= len(old) or old[i] != page]
for index, (number, page) in enumerate(delta):
    commit = len(new) if index == len(delta) - 1 else 0
    first = struct.pack(">II", number, commit)
    state = cksum(first + page, state)
    wal += first + struct.pack(">IIII", salt1, salt2, *state) + page
(ROOT / "gateway.db-wal").write_bytes(wal)
