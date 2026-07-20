"""Independent reference implementation of the ReleaseSentinel snapshot.

The verifier uses this to compute the expected snapshot for freshly minted badges, so a submission
cannot pass by hardcoding the shipped output.  It re-derives every decision from the trust policy
without reading the worker's code.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sentinel_kit as kit

# --- policy constants, as reconstructed from the incident-room archive ------------------------

RELEASE_SIGNING_KEYS = frozenset({"k-build-2026a", "k-build-2025b", "k-legacy-2024"})

LEGACY_REVOCATION = "2026-04-02T17:30:00.000Z"      # at/after -> revoked
LEGACY_EXCEPTION_SERVICE = "payments-api"
LEGACY_EXCEPTION_ID = "EX-14"
LEGACY_EXCEPTION_EXPIRY = "2026-06-30T00:00:00.000Z"  # at/after -> not covered
ROTATION_2025B_CUTOVER = "2026-05-01T00:00:00.000Z"   # at/after -> retired

STATUS_ORDER = [
    "badge_unreadable",
    "key_untrusted",
    "signature_invalid",
    "key_revoked",
    "tag_unknown",
    "branch_conflict",
    "accepted",
]

_SPKI_ED25519_PREFIX = bytes.fromhex("302a300506032b6570032100")
_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_ARTIFACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _epoch_ms(instant: str) -> int:
    parsed = dt.datetime.strptime(instant, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


# --- native-equivalent PNG payload extraction -------------------------------------------------


def extract_payload(png: bytes) -> bytes | None:
    """Return the concatenated ``atSt`` chunk data, or None if the badge carries no valid payload."""
    if len(png) < 8 or png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    offset = 8
    collected = bytearray()
    found = False
    while offset + 8 <= len(png):
        (length,) = struct.unpack(">I", png[offset : offset + 4])
        chunk_type = png[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        if data_end + 4 > len(png):
            return None
        data = png[data_start:data_end]
        (stored_crc,) = struct.unpack(">I", png[data_end : data_end + 4])
        import zlib

        if (zlib.crc32(chunk_type + data) & 0xFFFFFFFF) != stored_crc:
            return None
        if chunk_type == b"atSt":
            collected.extend(data)
            found = True
        if chunk_type == b"IEND":
            break
        offset = data_end + 4
    return bytes(collected) if found else None


# --- keyring ----------------------------------------------------------------------------------


def load_keyring(path: Path) -> dict[str, bytes]:
    """Return a mapping of key id to raw 32-byte Ed25519 public key."""
    document = json.loads(path.read_text(encoding="utf-8"))
    keys: dict[str, bytes] = {}
    for entry in document["keys"]:
        der = base64.b64decode(entry["public_key"])
        if not der.startswith(_SPKI_ED25519_PREFIX) or len(der) != len(_SPKI_ED25519_PREFIX) + 32:
            raise ValueError(f"unexpected key encoding for {entry['key_id']}")
        keys[entry["key_id"]] = der[len(_SPKI_ED25519_PREFIX) :]
    return keys


# --- repository (changelog is the branch source of truth) -------------------------------------

_CHANGELOG_HEADING = re.compile(r"^##\s+(\S+)\s+\(([^)]+)\)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Repository:
    tags: frozenset[str]
    tag_branch: dict[str, str]

    @classmethod
    def load(cls, root: Path) -> "Repository":
        import subprocess

        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        tag_branch = {match.group(1): match.group(2) for match in _CHANGELOG_HEADING.finditer(changelog)}
        result = subprocess.run(
            ["git", "-C", str(root), "tag", "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        tags = frozenset(line.strip() for line in result.stdout.split() if line.strip())
        return cls(tags=tags, tag_branch=tag_branch)


# --- the policy ------------------------------------------------------------------------------


def _is_instant(value: Any) -> bool:
    return isinstance(value, str) and bool(_INSTANT.match(value))


def _valid_statement(statement: Any) -> bool:
    if not isinstance(statement, dict):
        return False
    required = {
        "artifact_digest": str,
        "issued_at": str,
        "key_id": str,
        "release_branch": str,
        "release_tag": str,
        "service": str,
    }
    if set(statement) != set(required):
        return False
    for name, kind in required.items():
        if not isinstance(statement[name], kind) or statement[name] == "":
            return False
    if not _is_instant(statement["issued_at"]):
        return False
    return bool(_ARTIFACT_DIGEST.match(statement["artifact_digest"]))


def _key_status(key_id: str, service: str, issued_ms: int) -> tuple[str, str | None]:
    """Return (status, exception_id) for a trusted-in-keyring signing key at issue time."""
    if key_id == "k-legacy-2024":
        if issued_ms < _epoch_ms(LEGACY_REVOCATION):
            return "accepted", None
        if service == LEGACY_EXCEPTION_SERVICE and issued_ms < _epoch_ms(LEGACY_EXCEPTION_EXPIRY):
            return "accepted", LEGACY_EXCEPTION_ID
        return "key_revoked", None
    if key_id == "k-build-2025b":
        if issued_ms < _epoch_ms(ROTATION_2025B_CUTOVER):
            return "accepted", None
        return "key_revoked", None
    return "accepted", None


def evaluate_badge(
    name: str, png: bytes, keyring: dict[str, bytes], repository: Repository
) -> dict[str, Any]:
    """Return the snapshot record for one badge file."""
    payload = extract_payload(png)
    if payload is None:
        return _record(name, None, None, None, None, None, "badge_unreadable")
    try:
        attestation = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _record(name, None, None, None, None, None, "badge_unreadable")
    if not isinstance(attestation, dict) or set(attestation) != {"signature", "statement"}:
        return _record(name, None, None, None, None, None, "badge_unreadable")
    statement = attestation["statement"]
    if not _valid_statement(statement) or not isinstance(attestation["signature"], str):
        return _record(name, None, None, None, None, None, "badge_unreadable")

    key_id = statement["key_id"]
    service = statement["service"]
    tag = statement["release_tag"]
    claimed_branch = statement["release_branch"]
    issued_at = statement["issued_at"]

    if key_id not in keyring or key_id not in RELEASE_SIGNING_KEYS:
        return _record(name, service, key_id, tag, claimed_branch, None, "key_untrusted")

    try:
        signature = base64.b64decode(attestation["signature"], validate=True)
    except (ValueError, base64.binascii.Error):
        signature = b""
    preimage = kit.canonical_json(statement)
    if not kit.verify(keyring[key_id], preimage, signature):
        return _record(name, service, key_id, tag, claimed_branch, None, "signature_invalid")

    status, exception_id = _key_status(key_id, service, _epoch_ms(issued_at))
    if status == "key_revoked":
        return _record(name, service, key_id, tag, claimed_branch, None, "key_revoked")

    if tag not in repository.tags or tag not in repository.tag_branch:
        return _record(name, service, key_id, tag, claimed_branch, None, "tag_unknown")

    resolved_branch = repository.tag_branch[tag]
    if claimed_branch != resolved_branch and not resolved_branch.startswith("hotfix/"):
        return _record(name, service, key_id, tag, resolved_branch, None, "branch_conflict")

    return _record(name, service, key_id, tag, resolved_branch, exception_id, "accepted")


def _record(name, service, key_id, tag, branch, exception_id, status) -> dict[str, Any]:
    return {
        "badge": name,
        "exception_id": exception_id,
        "key_id": key_id,
        "release_branch": branch,
        "release_tag": tag,
        "service": service,
        "status": status,
    }


def build_snapshot(badge_dir: Path, repo_dir: Path, keyring_path: Path) -> dict[str, Any]:
    """Return the full expected snapshot object for a badge directory."""
    keyring = load_keyring(keyring_path)
    repository = Repository.load(repo_dir)
    badges = []
    for path in sorted(badge_dir.glob("*.png"), key=lambda p: p.name):
        badges.append(evaluate_badge(path.name, path.read_bytes(), keyring, repository))
    badges.sort(key=lambda record: record["badge"])

    counts = {status: 0 for status in STATUS_ORDER}
    for badge in badges:
        counts[badge["status"]] += 1

    digest = kit.sha256_hex(kit.canonical_json(badges))
    return {"badges": badges, "counts": counts, "digest": digest}
