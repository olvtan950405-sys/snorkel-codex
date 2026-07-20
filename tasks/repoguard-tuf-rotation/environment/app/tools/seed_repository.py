#!/usr/bin/env python3
"""Create the deterministic development repository and monotonic state."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("REPOGUARD_SEED_ROOT", "/app"))
REPO = APP / "repository"
META = REPO / "metadata"
TARGETS = REPO / "targets"
STATE = APP / "state"

SEEDS = {
    "old-a": "01" * 32,
    "old-b": "02" * 32,
    "root-a": "11" * 32,
    "root-b": "12" * 32,
    "root-c": "13" * 32,
    "timestamp-a": "21" * 32,
    "snapshot-a": "31" * 32,
    "targets-a": "41" * 32,
    "targets-b": "42" * 32,
    "plugins-a": "51" * 32,
    "private-a": "61" * 32,
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def key_material(seed_hex: str) -> tuple[bytes, str]:
    private = bytes.fromhex("302e020100300506032b657004220420" + seed_hex)
    with tempfile.TemporaryDirectory() as directory:
        private_path = Path(directory) / "key.der"
        public_path = Path(directory) / "pub.der"
        private_path.write_bytes(private)
        subprocess.run(
            ["openssl", "pkey", "-in", str(private_path), "-inform", "DER", "-pubout", "-outform", "DER", "-out", str(public_path)],
            check=True,
            capture_output=True,
        )
        public = public_path.read_bytes()
    return private, public[-32:].hex()


PRIVATE: dict[str, bytes] = {}
PUBLIC: dict[str, str] = {}
for _keyid, _seed in SEEDS.items():
    PRIVATE[_keyid], PUBLIC[_keyid] = key_material(_seed)


def sign_bytes(keyid: str, message: bytes) -> str:
    with tempfile.TemporaryDirectory() as directory:
        private = Path(directory) / "key.der"
        content = Path(directory) / "content"
        signature = Path(directory) / "sig"
        private.write_bytes(PRIVATE[keyid])
        content.write_bytes(message)
        subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-inkey", str(private), "-keyform", "DER", "-rawin", "-in", str(content), "-out", str(signature)],
            check=True,
            capture_output=True,
        )
        return signature.read_bytes().hex()


def envelope(signed: dict, signers: list[str]) -> dict:
    body = canonical(signed)
    return {"signatures": [{"keyid": keyid, "sig": sign_bytes(keyid, body)} for keyid in signers], "signed": signed}


def write_metadata(name: str, document: dict) -> Path:
    path = META / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(document) + b"\n")
    return path


def descriptor(path: Path, version: int) -> dict:
    raw = path.read_bytes()
    return {"hashes": {"sha256": hashlib.sha256(raw).hexdigest()}, "length": len(raw), "version": version}


def target_descriptor(path: Path) -> dict:
    raw = path.read_bytes()
    return {"hashes": {"sha256": hashlib.sha256(raw).hexdigest()}, "length": len(raw)}


def main() -> None:
    META.mkdir(parents=True, exist_ok=True)
    TARGETS.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)

    old_signed = {
        "_type": "root", "expires": "2028-01-01T00:00:00Z", "version": 1,
        "keys": {keyid: {"keytype": "ed25519", "public": PUBLIC[keyid], "scheme": "ed25519"} for keyid in ["old-a", "old-b"]},
        "roles": {"root": {"keyids": ["old-a", "old-b"], "threshold": 2}},
    }
    trusted_root = envelope(old_signed, ["old-a", "old-b"])
    (STATE / "trusted-root.json").write_bytes(canonical(trusted_root) + b"\n")

    all_new = ["root-a", "root-b", "root-c", "timestamp-a", "snapshot-a", "targets-a", "targets-b", "plugins-a", "private-a"]
    root_signed = {
        "_type": "root", "expires": "2028-01-01T00:00:00Z", "version": 2,
        "keys": {keyid: {"keytype": "ed25519", "public": PUBLIC[keyid], "scheme": "ed25519"} for keyid in all_new},
        "roles": {
            "root": {"keyids": ["root-a", "root-b", "root-c"], "threshold": 2},
            "timestamp": {"keyids": ["timestamp-a"], "threshold": 1},
            "snapshot": {"keyids": ["snapshot-a"], "threshold": 1},
            "targets": {"keyids": ["targets-a", "targets-b"], "threshold": 2},
        },
    }
    write_metadata("root.json", envelope(root_signed, ["old-a", "old-b", "root-a", "root-b"]))

    files = {
        "bin/api-v2.4.tar": b"api release 2.4\n",
        "bin/legacy.tar": b"legacy release was modified\n",
        "plugins/acme.zip": b"acme plugin 7\n",
        "plugins/private/ops.zip": b"private plugin must not fall through\n",
        "misc/orphan.txt": b"not described by metadata\n",
    }
    for name, body in files.items():
        path = TARGETS / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    good_legacy = b"original legacy release\n"
    top_signed = {
        "_type": "targets", "expires": "2027-01-01T00:00:00Z", "version": 7,
        "targets": {
            "bin/api-v2.4.tar": target_descriptor(TARGETS / "bin/api-v2.4.tar"),
            "bin/legacy.tar": {"hashes": {"sha256": hashlib.sha256(good_legacy).hexdigest()}, "length": len(good_legacy)},
            "bin/missing-debug.tar": {"hashes": {"sha256": hashlib.sha256(b"debug\n").hexdigest()}, "length": 6},
        },
        "delegations": {
            "keys": {
                "plugins-a": {"keytype": "ed25519", "public": PUBLIC["plugins-a"], "scheme": "ed25519"},
                "private-a": {"keytype": "ed25519", "public": PUBLIC["private-a"], "scheme": "ed25519"},
            },
            "roles": [
                {"keyids": ["private-a"], "name": "private", "paths": ["plugins/private/**"], "terminating": True, "threshold": 1},
                {"keyids": ["plugins-a"], "name": "plugins", "paths": ["plugins/**"], "terminating": False, "threshold": 1},
            ],
        },
    }
    targets_path = write_metadata("targets.json", envelope(top_signed, ["targets-a", "targets-b"]))

    plugins_signed = {
        "_type": "targets", "expires": "2027-01-01T00:00:00Z", "version": 4,
        "targets": {
            "plugins/acme.zip": target_descriptor(TARGETS / "plugins/acme.zip"),
            "plugins/private/ops.zip": target_descriptor(TARGETS / "plugins/private/ops.zip"),
        },
    }
    plugins_path = write_metadata("plugins.json", envelope(plugins_signed, ["plugins-a"]))
    private_signed = {"_type": "targets", "expires": "2027-01-01T00:00:00Z", "version": 3, "targets": {}}
    private_path = write_metadata("private.json", envelope(private_signed, ["private-a"]))

    snapshot_signed = {
        "_type": "snapshot", "expires": "2027-01-01T00:00:00Z", "version": 12,
        "meta": {
            "plugins.json": descriptor(plugins_path, 4),
            "private.json": descriptor(private_path, 3),
            "targets.json": descriptor(targets_path, 7),
        },
    }
    snapshot_path = write_metadata("snapshot.json", envelope(snapshot_signed, ["snapshot-a"]))
    timestamp_signed = {
        "_type": "timestamp", "expires": "2027-01-01T00:00:00Z", "version": 19,
        "meta": {"snapshot.json": descriptor(snapshot_path, 12)},
    }
    write_metadata("timestamp.json", envelope(timestamp_signed, ["timestamp-a"]))
    (REPO / "policy.json").write_bytes(canonical({"evaluation_time": "2026-07-01T00:00:00Z"}) + b"\n")

    database = STATE / "trust.db"
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE accepted(role TEXT PRIMARY KEY, version INTEGER NOT NULL)")
    connection.executemany("INSERT INTO accepted(role,version) VALUES(?,?)", [("root", 1), ("timestamp", 18), ("snapshot", 11), ("targets", 6), ("plugins", 3), ("private", 2)])
    connection.commit()
    connection.close()


if __name__ == "__main__":
    main()
