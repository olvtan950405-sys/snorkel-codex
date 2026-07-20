"""Verifier-side sealing kit for AtlasKey bundles.

This is the signing-station side of the format: it mints `.akb` archives, builds trust
catalogs, and derives the same keys the service is expected to derive. Tests use it to
produce bundles the task author never shipped, so a service that hardcodes anything about
the fixtures in /app/var/bundles cannot pass.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import io
import json
import struct
import tarfile
import zlib
from dataclasses import dataclass, field

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SUITE_KEY_BYTES = {
    "AES-256-GCM+HMAC-SHA256": 32,
    "AES-128-GCM+HMAC-SHA256": 16,
}

EVENT_COLUMNS = ("event_id", "occurred_at", "actor", "action", "resource", "risk", "amount_cents")
HIGH_RISK = ("high", "critical")

TAG_TENANT_ID = 0x01
TAG_KEY_ID = 0x02
TAG_KEY_EPOCH = 0x03
TAG_ALGORITHM = 0x04
TAG_SEALED_AT = 0x05
TAG_NONCE = 0x06
TAG_GCM_IV = 0x07
TAG_GCM_TAG = 0x08
TAG_CIPHERTEXT = 0x09


def canonical_json(value) -> str:
    """Object keys sorted by code point, compact separators, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_digest(rows: list[dict]) -> str:
    """SHA-256 over canonical rows, ordered by event_id, each followed by a newline."""
    ordered = sorted(rows, key=lambda row: row["event_id"])
    preimage = "".join(f"{canonical_json(row)}\n" for row in ordered)
    return sha256_hex(preimage.encode("utf-8"))


def high_risk_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if row["risk"] in HIGH_RISK)


def events_parquet(rows: list[dict]) -> bytes:
    table = pa.table(
        {
            "event_id": pa.array([row["event_id"] for row in rows], pa.string()),
            "occurred_at": pa.array([row["occurred_at"] for row in rows], pa.string()),
            "actor": pa.array([row["actor"] for row in rows], pa.string()),
            "action": pa.array([row["action"] for row in rows], pa.string()),
            "resource": pa.array([row["resource"] for row in rows], pa.string()),
            "risk": pa.array([row["risk"] for row in rows], pa.string()),
            "amount_cents": pa.array([row["amount_cents"] for row in rows], pa.int32()),
        }
    )
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="snappy")
    return sink.getvalue()


def derive_seal_keys(root_secret: bytes, salt_hex: str, enc_key_bytes: int) -> tuple[bytes, bytes]:
    salt = bytes.fromhex(salt_hex)
    mac_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"atlaskey/seal/mac").derive(root_secret)
    enc_key = HKDF(
        algorithm=hashes.SHA256(), length=enc_key_bytes, salt=salt, info=b"atlaskey/seal/enc"
    ).derive(root_secret)
    return mac_key, enc_key


def seal_aad(tenant_id: str, key_epoch: int, algorithm: str) -> bytes:
    return f"{tenant_id}|{key_epoch}|{algorithm}".encode("utf-8")


@dataclass
class SealInputs:
    tenant_id: str
    key_id: str
    key_epoch: int
    algorithm: str
    sealed_at_ms: int
    nonce: bytes
    gcm_iv: bytes
    payload: dict
    mac_key: bytes
    enc_key: bytes


def _record(tag: int, value: bytes) -> bytes:
    return struct.pack("<BH", tag, len(value)) + value


def seal_v2(
    inputs: SealInputs,
    extra_records: list[tuple[int, bytes]] | None = None,
    flip_ciphertext: bool = False,
) -> bytes:
    """Build a version 2 seal footer: little-endian, 4-byte aligned TLV records, MAC, CRC-32."""
    aad = seal_aad(inputs.tenant_id, inputs.key_epoch, inputs.algorithm)
    sealed = AESGCM(inputs.enc_key).encrypt(inputs.gcm_iv, canonical_json(inputs.payload).encode("utf-8"), aad)
    ciphertext, gcm_tag = sealed[:-16], sealed[-16:]

    body = b""
    ciphertext_end = 0
    for tag, value in [
        (TAG_TENANT_ID, inputs.tenant_id.encode("utf-8")),
        (TAG_KEY_ID, inputs.key_id.encode("utf-8")),
        (TAG_KEY_EPOCH, struct.pack("<I", inputs.key_epoch)),
        (TAG_ALGORITHM, inputs.algorithm.encode("utf-8")),
        (TAG_SEALED_AT, struct.pack("<q", inputs.sealed_at_ms)),
        (TAG_NONCE, inputs.nonce),
        (TAG_GCM_IV, inputs.gcm_iv),
        (TAG_GCM_TAG, gcm_tag),
        (TAG_CIPHERTEXT, ciphertext),
    ] + list(extra_records or []):
        body += _record(tag, value)
        if tag == TAG_CIPHERTEXT:
            ciphertext_end = len(body)
        body += b"\x00" * (-len(body) % 4)

    covered = bytearray(b"AKB2" + struct.pack("<HHI", 2, 0, len(body)) + body)
    mac = hmac.new(inputs.mac_key, bytes(covered), hashlib.sha256).digest()

    if flip_ciphertext:
        # Flip a byte of the sealed payload *after* the station signed it, then repair the
        # transport CRC: the archive looks intact to a reader that only checks the CRC.
        covered[12 + ciphertext_end - 1] ^= 0x01

    footer = bytes(covered) + mac
    return footer + struct.pack("<I", zlib.crc32(footer) & 0xFFFFFFFF)


def seal_v1(inputs: SealInputs) -> bytes:
    """Build a legacy version 1 seal footer: big-endian, fixed field order, no nonce, no CRC."""
    aad = seal_aad(inputs.tenant_id, inputs.key_epoch, inputs.algorithm)
    sealed = AESGCM(inputs.enc_key).encrypt(inputs.gcm_iv, canonical_json(inputs.payload).encode("utf-8"), aad)
    ciphertext, gcm_tag = sealed[:-16], sealed[-16:]

    tenant = inputs.tenant_id.encode("utf-8")
    algorithm = inputs.algorithm.encode("utf-8")
    covered = (
        b"AKB1"
        + struct.pack(">HH", 1, 0)
        + bytes([len(tenant)])
        + tenant
        + bytes([len(algorithm)])
        + algorithm
        + struct.pack(">I", inputs.key_epoch)
        + struct.pack(">q", inputs.sealed_at_ms)
        + inputs.gcm_iv
        + gcm_tag
        + struct.pack(">I", len(ciphertext))
        + ciphertext
    )
    return covered + hmac.new(inputs.mac_key, covered, hashlib.sha256).digest()


def read_members(archive: bytes) -> dict[str, bytes]:
    """Pull the members back out of a packed archive."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        return {
            member.name: tar.extractfile(member).read() for member in tar.getmembers() if member.isfile()
        }


def pack_members(members: list[tuple[str, bytes]]) -> bytes:
    """Uncompressed ustar archive holding exactly the given members."""
    sink = io.BytesIO()
    with tarfile.open(fileobj=sink, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, payload in members:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = 1748000000
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(payload))
    return sink.getvalue()


def pack_bundle(manifest_bytes: bytes, events_bytes: bytes, seal_bytes: bytes) -> bytes:
    """The three members a real bundle carries."""
    return pack_members(
        [
            ("manifest.json", manifest_bytes),
            ("events.parquet", events_bytes),
            ("seal.bin", seal_bytes),
        ]
    )


@dataclass
class Epoch:
    tenant_id: str
    epoch: int
    key_id: str
    salt_hex: str
    root_secret: bytes
    valid_from: str
    valid_until: str | None


@dataclass
class Catalog:
    tenants: list[tuple[str, str, str]] = field(default_factory=list)  # id, display name, status
    epochs: list[Epoch] = field(default_factory=list)
    algorithms: list[tuple[str, str]] = field(default_factory=list)
    revocations: list[tuple[str, str, str]] = field(default_factory=list)  # key id, instant, reason
    ledger: list[tuple[str, str, str, str, str]] = field(default_factory=list)

    def epoch_for(self, tenant_id: str, epoch: int) -> Epoch:
        for row in self.epochs:
            if row.tenant_id == tenant_id and row.epoch == epoch:
                return row
        raise KeyError(f"{tenant_id}/{epoch}")

    def keyring(self) -> dict:
        keyring: dict[str, dict[str, str]] = {}
        for row in self.epochs:
            keyring.setdefault(row.tenant_id, {})[str(row.epoch)] = base64.b64encode(row.root_secret).decode()
        return keyring

    def write(self, db_path: str) -> None:
        connection = duckdb.connect(db_path)
        connection.execute(SCHEMA_SQL)
        for tenant in self.tenants:
            connection.execute("INSERT INTO tenants VALUES (?, ?, ?)", list(tenant))
        for row in self.epochs:
            connection.execute(
                "INSERT INTO key_epochs VALUES (?, ?, ?, ?, ?, ?)",
                [row.tenant_id, row.epoch, row.key_id, row.salt_hex, row.valid_from, row.valid_until],
            )
        for pair in self.algorithms:
            connection.execute("INSERT INTO allowed_algorithms VALUES (?, ?)", list(pair))
        for revocation in self.revocations:
            connection.execute("INSERT INTO revoked_keys VALUES (?, ?, ?)", list(revocation))
        for entry in self.ledger:
            connection.execute("INSERT INTO seal_ledger VALUES (?, ?, ?, ?, ?)", list(entry))
        connection.close()


SCHEMA_SQL = """
CREATE TABLE tenants (
    tenant_id VARCHAR PRIMARY KEY,
    display_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL
);
CREATE TABLE key_epochs (
    tenant_id VARCHAR NOT NULL,
    epoch INTEGER NOT NULL,
    key_id VARCHAR NOT NULL,
    salt_hex VARCHAR NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_until TIMESTAMP,
    PRIMARY KEY (tenant_id, epoch)
);
CREATE TABLE allowed_algorithms (
    tenant_id VARCHAR NOT NULL,
    algorithm VARCHAR NOT NULL,
    PRIMARY KEY (tenant_id, algorithm)
);
CREATE TABLE revoked_keys (
    key_id VARCHAR PRIMARY KEY,
    revoked_at TIMESTAMP NOT NULL,
    reason VARCHAR NOT NULL
);
CREATE TABLE seal_ledger (
    nonce_hex VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    bundle_id VARCHAR NOT NULL,
    key_id VARCHAR NOT NULL,
    sealed_at TIMESTAMP NOT NULL
);
"""


@dataclass
class Bundle:
    bundle_id: str
    archive: bytes
    rows: list[dict]
    nonce_hex: str
    tenant_id: str
    key_epoch: int
    sealed_at_ms: int
    manifest_digest: str
    content_digest: str


def mint_bundle(
    *,
    bundle_id: str,
    epoch: Epoch,
    rows: list[dict],
    sealed_at_ms: int,
    nonce: bytes,
    gcm_iv: bytes,
    algorithm: str = "AES-256-GCM+HMAC-SHA256",
    key_id: str | None = None,
    tenant_id: str | None = None,
    key_epoch: int | None = None,
    enc_epoch: Epoch | None = None,
    version: int = 2,
    payload_overrides: dict | None = None,
    corrupt_rows: list[dict] | None = None,
    corrupt_manifest: dict | None = None,
    corrupt_crc: bool = False,
    flip_ciphertext: bool = False,
    extra_records: list[tuple[int, bytes]] | None = None,
) -> Bundle:
    """Seal a bundle. The override arguments exist to build bundles a good station never would."""
    tenant_id = tenant_id or epoch.tenant_id
    key_epoch = epoch.epoch if key_epoch is None else key_epoch
    key_id = key_id or epoch.key_id

    manifest = {
        "bundle_id": bundle_id,
        "tenant_id": tenant_id,
        "station_id": "sign-station-04",
        "produced_at": iso_ms(sealed_at_ms),
        "event_file": "events.parquet",
        "event_count": len(rows),
    }
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")

    payload = {
        "content_digest": content_digest(rows),
        "event_count": len(rows),
        "manifest_digest": sha256_hex(manifest_bytes),
    }
    if payload_overrides:
        payload.update(payload_overrides)

    enc_key_bytes = SUITE_KEY_BYTES.get(algorithm, 32)
    mac_key, _ = derive_seal_keys(epoch.root_secret, epoch.salt_hex, enc_key_bytes)
    key_source = enc_epoch or epoch
    _, enc_key = derive_seal_keys(key_source.root_secret, key_source.salt_hex, enc_key_bytes)

    inputs = SealInputs(
        tenant_id=tenant_id,
        key_id=key_id,
        key_epoch=key_epoch,
        algorithm=algorithm,
        sealed_at_ms=sealed_at_ms,
        nonce=nonce,
        gcm_iv=gcm_iv,
        payload=payload,
        mac_key=mac_key,
        enc_key=enc_key,
    )
    if version == 1:
        seal_bytes = seal_v1(inputs)
    else:
        seal_bytes = seal_v2(inputs, extra_records=extra_records, flip_ciphertext=flip_ciphertext)

    if corrupt_crc:
        seal_bytes = seal_bytes[:-4] + bytes([seal_bytes[-4] ^ 0x01]) + seal_bytes[-3:]

    # Bodies can be swapped out after sealing: that is what a tampered bundle is.
    shipped_rows = corrupt_rows if corrupt_rows is not None else rows
    shipped_manifest = manifest_bytes
    if corrupt_manifest is not None:
        shipped_manifest = (canonical_json(corrupt_manifest) + "\n").encode("utf-8")

    archive = pack_bundle(shipped_manifest, events_parquet(shipped_rows), seal_bytes)

    return Bundle(
        bundle_id=bundle_id,
        archive=archive,
        rows=shipped_rows,
        nonce_hex=nonce.hex(),
        tenant_id=tenant_id,
        key_epoch=key_epoch,
        sealed_at_ms=sealed_at_ms,
        manifest_digest=sha256_hex(shipped_manifest),
        content_digest=content_digest(shipped_rows),
    )


def iso_ms(ms: int) -> str:
    moment = datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def make_rows(rng, count: int) -> list[dict]:
    actions = ("key.rotate", "vault.open", "policy.update", "export.run", "session.start")
    resources = ("vault/alpha", "vault/beta", "policy/root", "export/nightly")
    risks = ("low", "medium", "high", "critical")
    rows = []
    for index in range(count):
        rows.append(
            {
                "event_id": f"evt-{index:05d}",
                "occurred_at": iso_ms(1747000000000 + index * 61000),
                "actor": f"user-{rng.randrange(1, 40):03d}",
                "action": rng.choice(actions),
                "resource": rng.choice(resources),
                "risk": rng.choice(risks),
                "amount_cents": rng.randrange(-5000, 250000),
            }
        )
    return rows
