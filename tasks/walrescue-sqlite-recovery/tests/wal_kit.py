"""Independent SQLite WAL fixture builder used only by the verifier."""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path


def words(data: bytes, endian: str):
    fmt = "<II" if endian == "little" else ">II"
    for offset in range(0, len(data), 8):
        yield struct.unpack_from(fmt, data, offset)


def checksum(data: bytes, state=(0, 0), endian="little"):
    s0, s1 = state
    for x0, x1 in words(data, endian):
        s0 = (s0 + x0 + s1) & 0xFFFFFFFF
        s1 = (s1 + x1 + s0) & 0xFFFFFFFF
    return s0, s1


def pages(blob: bytes, page_size: int) -> list[bytes]:
    assert len(blob) % page_size == 0
    return [blob[i : i + page_size] for i in range(0, len(blob), page_size)]


def changed(before: bytes, after: bytes, page_size: int) -> list[tuple[int, bytes]]:
    old = pages(before, page_size)
    new = pages(after, page_size)
    return [(i + 1, page) for i, page in enumerate(new) if i >= len(old) or old[i] != page]


@dataclass
class WalBuild:
    blob: bytearray
    frame_offsets: list[int]
    committed_frames: int
    transactions: int
    database_pages: int


def build_wal(
    base: bytes,
    snapshots: list[bytes],
    page_size: int,
    endian: str,
    salt1: int,
    salt2: int,
    uncommitted: bytes | None = None,
) -> WalBuild:
    magic = 0x377F0682 if endian == "little" else 0x377F0683
    header_first = struct.pack(">IIIIII", magic, 3007000, page_size, 0, salt1, salt2)
    h0, h1 = checksum(header_first, endian=endian)
    out = bytearray(header_first + struct.pack(">II", h0, h1))
    state = (h0, h1)
    offsets = []
    previous = base
    committed = 0
    for snapshot in snapshots:
        delta = changed(previous, snapshot, page_size)
        assert delta
        db_pages = len(snapshot) // page_size
        for index, (page_number, page) in enumerate(delta):
            commit_size = db_pages if index == len(delta) - 1 else 0
            first = struct.pack(">II", page_number, commit_size)
            state = checksum(first + page, state, endian)
            offsets.append(len(out))
            out += first + struct.pack(">IIII", salt1, salt2, *state) + page
        committed += len(delta)
        previous = snapshot
    if uncommitted is not None:
        for page_number, page in changed(previous, uncommitted, page_size):
            first = struct.pack(">II", page_number, 0)
            state = checksum(first + page, state, endian)
            offsets.append(len(out))
            out += first + struct.pack(">IIII", salt1, salt2, *state) + page
    return WalBuild(out, offsets, committed, len(snapshots), len(snapshots[-1]) // page_size)


def snapshot(path: Path) -> bytes:
    return path.read_bytes()


def make_database_history(root: Path, rng: random.Random, page_size=1024):
    path = root / "working.db"
    con = sqlite3.connect(path)
    con.execute(f"PRAGMA page_size={page_size}")
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("VACUUM")
    con.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, device TEXT, reading INTEGER, note TEXT)")
    rows = [
        (i, f"sensor-{rng.randrange(20)}", rng.randrange(-500, 500), f"base-{rng.getrandbits(48):012x}")
        for i in range(1, 90)
    ]
    con.executemany("INSERT INTO events VALUES(?,?,?,?)", rows)
    con.commit()
    base = snapshot(path)

    con.executemany(
        "UPDATE events SET reading=?, note=? WHERE id=?",
        [(rng.randrange(1000, 9000), f"tx1-{rng.getrandbits(48):012x}", i) for i in range(7, 70, 7)],
    )
    con.executemany(
        "INSERT INTO events(device,reading,note) VALUES(?,?,?)",
        [(f"edge-{i}", rng.randrange(9000), "first") for i in range(45)],
    )
    con.commit()
    first = snapshot(path)

    con.execute("DELETE FROM events WHERE id % 5 = 0")
    con.executemany(
        "INSERT INTO events(device,reading,note) VALUES(?,?,?)",
        [(f"final-{i}", rng.randrange(-10000, 10000), f"tx2-{rng.getrandbits(32):08x}") for i in range(35)],
    )
    con.commit()
    second = snapshot(path)

    con.execute("UPDATE events SET note='not-committed', reading=reading+12345 WHERE id % 3 = 0")
    con.commit()
    tail = snapshot(path)
    con.close()
    return base, first, second, tail


def expected_report(build: WalBuild, page_size: int, output: bytes, stop="end_of_wal", scanned=None, valid=None):
    if valid is None:
        valid = len(build.frame_offsets)
    if scanned is None:
        scanned = valid
    return {
        "status": "recovered",
        "page_size": page_size,
        "frames_scanned": scanned,
        "valid_frames": valid,
        "committed_frames": build.committed_frames,
        "transactions": build.transactions,
        "database_pages": build.database_pages,
        "ignored_tail_frames": valid - build.committed_frames,
        "stop_reason": stop,
        "output_sha256": hashlib.sha256(output).hexdigest(),
    }


def standalone(blob: bytes) -> bytes:
    result = bytearray(blob)
    result[18:20] = b"\x01\x01"
    return bytes(result)


def run_tool(root: Path, db: bytes, wal: bytes):
    db_path = root / "input.db"
    wal_path = root / "input.db-wal"
    out_path = root / "recovered.db"
    report_path = root / "report.json"
    db_path.write_bytes(db)
    wal_path.write_bytes(wal)
    result = subprocess.run(
        [
            os.environ.get("WALRESCUE_BIN", "/app/bin/walrescue"),
            "recover", "--db", str(db_path), "--wal", str(wal_path),
            "--out", str(out_path), "--report", str(report_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, out_path, report_path


def assert_database(blob_path: Path, expected_blob: bytes):
    assert blob_path.read_bytes() == standalone(expected_blob)
    con = sqlite3.connect(f"file:{blob_path}?mode=ro&immutable=1", uri=True)
    assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    con.execute("SELECT count(*), sum(reading) FROM events").fetchone()
    con.close()


def load_report(path: Path):
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    parsed = json.loads(raw)
    expected_order = [
        "status", "page_size", "frames_scanned", "valid_frames", "committed_frames",
        "transactions", "database_pages", "ignored_tail_frames", "stop_reason", "output_sha256",
    ]
    assert list(parsed) == expected_order
    assert raw == json.dumps(parsed, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
    return parsed
