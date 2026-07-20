"""Dynamic fixture construction for GlacierVault verifier tests."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path


NOW = 1782000000000
APP = Path(os.environ.get("BACKUPGUARD_APP", "/app"))


def _head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")


def cbor(value: object, canonical: bool = True) -> bytes:
    """Encode the deliberately small manifest data model as CBOR."""
    if isinstance(value, int):
        return _head(0, value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode()
        return _head(3, len(raw)) + raw
    if isinstance(value, list):
        return _head(4, len(value)) + b"".join(cbor(item, canonical) for item in value)
    if isinstance(value, dict):
        pairs = [(cbor(key), cbor(item, canonical)) for key, item in value.items()]
        if canonical:
            pairs.sort(key=lambda pair: (len(pair[0]), pair[0]))
        else:
            pairs.reverse()
        return _head(5, len(pairs)) + b"".join(key + item for key, item in pairs)
    raise TypeError(type(value))


def _merkle(digests: list[bytes]) -> bytes:
    level = [hashlib.sha256(b"\x00" + digest).digest() for digest in digests]
    while len(level) > 1:
        level = [
            hashlib.sha256(b"\x01" + level[index] + level[min(index + 1, len(level) - 1)]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def _key(root: Path, name: str) -> tuple[Path, bytes]:
    private = root / f"{name}.pem"
    public = root / f"{name}.der"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", private], check=True)
    subprocess.run(
        ["openssl", "pkey", "-in", private, "-pubout", "-outform", "DER", "-out", public], check=True
    )
    return private, public.read_bytes()[-32:]


def _sign(private: Path, payload: bytes, root: Path, name: str) -> bytes:
    source, target = root / f"{name}.msg", root / f"{name}.sig"
    source.write_bytes(payload)
    subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", private, "-in", source, "-out", target],
        check=True,
    )
    return target.read_bytes()


def build_case(root: Path, case: str = "accepted") -> tuple[Path, Path]:
    """Create a fresh signed bundle and trust catalog for one behavior case."""
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    contents = [b"alpha backup segment\n", b"second segment with different bytes\n", b"tail\n"]
    digests: list[bytes] = []
    segments = []
    for index, content in enumerate(contents):
        name = f"part-{index + 1}.bin"
        (bundle / name).write_bytes(content)
        digest = hashlib.sha256(content).digest()
        digests.append(digest)
        segments.append({"name": name, "size": len(content), "sha256": digest})
    tenant = "missing" if case == "tenant_unknown" else "northwind"
    manifest = {
        "bundle_id": "vault-2026-0621-a",
        "tenant": tenant,
        "created_at": NOW,
        "nonce": hashlib.sha256(str(root).encode()).digest()[:16],
        "segments": segments,
        "merkle_root": _merkle(digests),
    }
    if case == "merkle":
        manifest["merkle_root"] = b"\x99" * 32
    raw = cbor(manifest, canonical=case != "noncanonical")
    (bundle / "manifest.cbor").write_bytes(raw)

    operator_private, operator_public = _key(root, "operator")
    recovery_private, recovery_public = _key(root, "recovery")
    signatures = [
        {"key_id": "op-1", "signature": base64.b64encode(_sign(operator_private, raw, root, "op")).decode()},
        {"key_id": "rec-1", "signature": base64.b64encode(_sign(recovery_private, raw, root, "rec")).decode()},
    ]
    if case == "quorum":
        signatures.pop()
    if case == "invalid_signature":
        signatures[1]["signature"] = base64.b64encode(b"x" * 64).decode()
    (bundle / "signatures.json").write_text(json.dumps(signatures), encoding="utf-8")
    if case == "segment":
        (bundle / "part-2.bin").write_bytes(b"tampered")

    catalog = root / "trust.db"
    connection = sqlite3.connect(catalog)
    connection.executescript((APP / "docs/catalog-schema.sql").read_text())
    connection.execute("INSERT INTO tenants VALUES('northwind','active')")
    revoked = NOW - 1 if case in {"revoked", "exception"} else None
    connection.execute("INSERT INTO keys VALUES(?,?,?,?,?,?,?)", ("op-1", "northwind", "operator", operator_public, 1768176000000, None, revoked))
    connection.execute("INSERT INTO keys VALUES(?,?,?,?,?,?,?)", ("rec-1", "northwind", "recovery", recovery_public, 1768176000000, None, None))
    connection.execute("INSERT INTO quorum_policies VALUES(?,?,?,?,?)", ("northwind", 1768176000000, 2, 0, 2))
    connection.execute("INSERT INTO quorum_policies VALUES(?,?,?,?,?)", ("northwind", 1780272000000, 1, 1, 2))
    if case == "exception":
        connection.execute(
            "INSERT INTO emergency_exceptions VALUES(?,?,?,?,?,?)",
            ("exc-7", "northwind", "op-1", NOW - 1000, NOW + 1000, "vault-2026-"),
        )
    connection.commit()
    connection.close()
    return bundle, catalog


def run_guard(bundle: Path, catalog: Path, output: Path, *, build: bool = True) -> dict[str, object]:
    """Build and invoke the submitted verifier, returning its JSON verdict."""
    if build:
        subprocess.run(["go", "build", "-o", APP / "bin/backupguard", "./cmd/backupguard"], cwd=APP, check=True)
    subprocess.run(
        [APP / "bin/backupguard", "verify", "--bundle", str(bundle), "--catalog", str(catalog), "--out", str(output)],
        check=True,
    )
    raw = output.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    return json.loads(raw)
