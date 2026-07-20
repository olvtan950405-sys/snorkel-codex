"""End-to-end checks for the AtlasKey audit service.

Nothing here reuses the bundles, the trust catalog or the key material shipped in the image.
Every run mints its own tenants, epochs, root secrets, event tables and seals with the kit in
/tests/akb_kit.py, points the service at them, and compares the verdicts against what the
contract in /app/docs/audit-api.md requires.
"""

import datetime
import hashlib
import json
import os
import random
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from akb_kit import (  # noqa: E402
    Catalog,
    Epoch,
    canonical_json,
    high_risk_count,
    iso_ms,
    make_rows,
    mint_bundle,
    pack_members,
    read_members,
)

APP = Path("/app")
SERVICE = APP / "bin" / "atlaskey-audit.js"

AES_256 = "AES-256-GCM+HMAC-SHA256"
AES_128 = "AES-128-GCM+HMAC-SHA256"


def ms(iso_day: str) -> int:
    day = datetime.datetime.strptime(iso_day, "%Y-%m-%d").replace(hour=12, tzinfo=datetime.timezone.utc)
    return int(day.timestamp() * 1000)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(base: str, path: str, method: str) -> dict:
    call = urllib.request.Request(f"{base}{path}", method=method)
    try:
        with urllib.request.urlopen(call, timeout=60) as response:
            raw = response.read()
            headers = response.headers
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        headers = error.headers
        status = error.code
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = None
    return {
        "status": status,
        "raw": raw,
        "body": body,
        "content_type": headers.get("content-type", ""),
    }


class Workspace:
    def __init__(self, catalog, bundles, results, ledger):
        self.catalog = catalog
        self.bundles = bundles
        self.results = results
        self.ledger = ledger

    def verdict(self, name: str) -> dict:
        return self.results[name]["body"]

    def reasons(self, name: str) -> list:
        return self.verdict(name)["reasons"]


def build_catalog(rng: random.Random) -> Catalog:
    """A trust catalog with nothing in common with the one shipped in the image."""

    def epoch(tenant, number, key_id, valid_from, valid_until) -> Epoch:
        return Epoch(
            tenant_id=tenant,
            epoch=number,
            key_id=key_id,
            salt_hex=bytes(rng.randrange(256) for _ in range(32)).hex(),
            root_secret=bytes(rng.randrange(256) for _ in range(32)),
            valid_from=valid_from,
            valid_until=valid_until,
        )

    catalog = Catalog()
    catalog.tenants = [
        ("quarry-east", "Quarry East Signing", "active"),
        ("delta-ridge", "Delta Ridge Signing", "active"),
        ("harbor-mist", "Harbor Mist Signing", "suspended"),
    ]
    catalog.epochs = [
        epoch("quarry-east", 6, "quarry-east-2025h2", "2025-06-01 00:00:00", "2026-01-01 00:00:00"),
        epoch("quarry-east", 7, "quarry-east-2026h1", "2026-01-01 00:00:00", None),
        epoch("quarry-east", 8, "quarry-east-2026h2", "2026-08-01 00:00:00", None),
        epoch("delta-ridge", 2, "delta-ridge-2026h1", "2026-02-01 00:00:00", None),
        epoch("harbor-mist", 1, "harbor-mist-2025h1", "2025-01-01 00:00:00", None),
        # Key material exists for a station that was never onboarded as a tenant.
        epoch("ghost-north", 5, "ghost-north-2026h1", "2026-01-01 00:00:00", None),
    ]
    catalog.algorithms = [
        ("quarry-east", AES_256),
        ("delta-ridge", AES_256),
        ("delta-ridge", AES_128),
        ("harbor-mist", AES_256),
    ]
    catalog.revocations = [
        ("quarry-east-2025h2", "2026-01-15 00:00:00", "station decommissioned"),
        ("delta-ridge-2026h1", "2026-06-01 00:00:00", "key material leaked in a backup"),
    ]
    return catalog


def mint_all(catalog: Catalog, rng: random.Random) -> dict:
    """One bundle for each behaviour the contract describes."""
    quarry6 = catalog.epoch_for("quarry-east", 6)
    quarry7 = catalog.epoch_for("quarry-east", 7)
    quarry8 = catalog.epoch_for("quarry-east", 8)
    delta2 = catalog.epoch_for("delta-ridge", 2)
    harbor1 = catalog.epoch_for("harbor-mist", 1)
    ghost5 = catalog.epoch_for("ghost-north", 5)

    bundles = {}

    def mint(name, **kwargs):
        bundles[name] = mint_bundle(
            bundle_id=name,
            nonce=bytes(rng.randrange(256) for _ in range(16)),
            gcm_iv=bytes(rng.randrange(256) for _ in range(12)),
            **kwargs,
        )

    mint("clean-quarry", epoch=quarry7, rows=make_rows(rng, 57), sealed_at_ms=ms("2026-05-04"))
    mint(
        "clean-delta-aes128",
        epoch=delta2,
        rows=make_rows(rng, 33),
        sealed_at_ms=ms("2026-05-05"),
        algorithm=AES_128,
    )
    mint(
        "clean-unknown-record",
        epoch=quarry7,
        rows=make_rows(rng, 21),
        sealed_at_ms=ms("2026-05-06"),
        extra_records=[(0x40, b"station-firmware-4.2.1")],
    )
    mint("revoked-key", epoch=delta2, rows=make_rows(rng, 19), sealed_at_ms=ms("2026-06-02"))
    mint("before-revocation", epoch=delta2, rows=make_rows(rng, 17), sealed_at_ms=ms("2026-05-20"))
    mint("epoch-expired", epoch=quarry6, rows=make_rows(rng, 15), sealed_at_ms=ms("2026-01-05"))
    mint("expired-and-revoked", epoch=quarry6, rows=make_rows(rng, 14), sealed_at_ms=ms("2026-02-10"))
    mint("epoch-not-yet-valid", epoch=quarry8, rows=make_rows(rng, 13), sealed_at_ms=ms("2026-03-10"))
    mint(
        "algorithm-not-allowed",
        epoch=quarry7,
        rows=make_rows(rng, 12),
        sealed_at_ms=ms("2026-05-07"),
        algorithm=AES_128,
    )
    mint(
        "unsupported-algorithm",
        epoch=quarry7,
        rows=make_rows(rng, 11),
        sealed_at_ms=ms("2026-05-08"),
        algorithm="AES-256-CTR+HMAC-SHA512",
    )
    mint("tenant-suspended", epoch=harbor1, rows=make_rows(rng, 10), sealed_at_ms=ms("2026-05-09"))
    mint("unknown-tenant", epoch=ghost5, rows=make_rows(rng, 9), sealed_at_ms=ms("2026-05-10"))
    mint("unknown-epoch", epoch=quarry7, rows=make_rows(rng, 8), sealed_at_ms=ms("2026-05-11"), key_epoch=99)
    mint(
        "key-id-mismatch",
        epoch=quarry7,
        rows=make_rows(rng, 16),
        sealed_at_ms=ms("2026-05-12"),
        key_id="quarry-east-rogue",
    )

    rows = make_rows(rng, 26)
    edited = [dict(row) for row in rows]
    edited[9]["actor"] = "user-999"
    edited[9]["risk"] = "critical"
    mint("rows-edited", epoch=quarry7, rows=rows, corrupt_rows=edited, sealed_at_ms=ms("2026-05-13"))

    rows = make_rows(rng, 24)
    mint("row-dropped", epoch=quarry7, rows=rows, corrupt_rows=rows[:-1], sealed_at_ms=ms("2026-05-14"))

    mint(
        "manifest-edited",
        epoch=quarry7,
        rows=make_rows(rng, 18),
        sealed_at_ms=ms("2026-05-15"),
        corrupt_manifest={
            "bundle_id": "manifest-edited",
            "tenant_id": "quarry-east",
            "station_id": "sign-station-99",
            "produced_at": iso_ms(ms("2026-05-15")),
            "event_file": "events.parquet",
            "event_count": 18,
        },
    )
    mint(
        "payload-wrong-key",
        epoch=quarry7,
        enc_epoch=quarry6,
        rows=make_rows(rng, 20),
        sealed_at_ms=ms("2026-05-16"),
    )
    mint(
        "ciphertext-flipped",
        epoch=quarry7,
        rows=make_rows(rng, 22),
        sealed_at_ms=ms("2026-05-17"),
        flip_ciphertext=True,
    )
    mint("crc-flipped", epoch=quarry7, rows=make_rows(rng, 23), sealed_at_ms=ms("2026-05-18"), corrupt_crc=True)
    mint("legacy-v1", epoch=quarry7, rows=make_rows(rng, 25), sealed_at_ms=ms("2026-05-19"), version=1)
    return bundles


@pytest.fixture(scope="session")
def workspace():
    """Mint a private catalog, keyring and bundle set, then run the service against them."""
    rng = random.Random(secrets.randbits(64))
    root = Path(tempfile.mkdtemp(prefix="akb-verify-"))
    bundle_dir = root / "bundles"
    bundle_dir.mkdir()

    catalog = build_catalog(rng)
    db_path = root / "trust-catalog.duckdb"
    catalog.write(str(db_path))
    keyring_path = root / "keyring.json"
    keyring_path.write_text(json.dumps(catalog.keyring(), indent=2), encoding="utf-8")

    bundles = mint_all(catalog, rng)
    for bundle in bundles.values():
        (bundle_dir / f"{bundle.bundle_id}.akb").write_bytes(bundle.archive)

    # Three archives that are not usable bundles.
    (bundle_dir / "garbage.akb").write_bytes(secrets.token_bytes(4096))
    clean = bundles["clean-quarry"]
    members = read_members(clean.archive)
    (bundle_dir / "seal-missing.akb").write_bytes(
        pack_members([("manifest.json", members["manifest.json"]), ("events.parquet", members["events.parquet"])])
    )
    (bundle_dir / "events-unreadable.akb").write_bytes(
        pack_members(
            [
                ("manifest.json", members["manifest.json"]),
                ("events.parquet", secrets.token_bytes(2048)),
                ("seal.bin", members["seal.bin"]),
            ]
        )
    )

    env = dict(os.environ)
    env["ATLASKEY_TRUST_CATALOG"] = str(db_path)
    env["ATLASKEY_KEYRING_PATH"] = str(keyring_path)
    env["ATLASKEY_BUNDLE_DIR"] = str(bundle_dir)

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = root / "service.log"
    log = log_path.open("wb")
    server = subprocess.Popen(
        ["node", str(SERVICE), "--port", str(port)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=str(APP),
    )

    deadline = time.time() + 60
    started = False
    while time.time() < deadline:
        if server.poll() is not None:
            break
        try:
            if request(base, "/healthz", "GET")["status"] == 200:
                started = True
                break
        except Exception:
            time.sleep(0.25)
    if not started:
        server.terminate()
        log.close()
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        pytest.fail(f"the audit service did not come up:\n{tail}")

    try:
        results = {}
        for name in list(bundles) + ["garbage", "seal-missing", "events-unreadable"]:
            results[name] = request(base, f"/audit-bundles/{name}/verify", "POST")
        # A clean bundle, submitted a second time.
        results["clean-quarry-again"] = request(base, "/audit-bundles/clean-quarry/verify", "POST")
        # A rejected bundle, submitted a second time.
        results["rows-edited-again"] = request(base, "/audit-bundles/rows-edited/verify", "POST")
        results["missing"] = request(base, "/audit-bundles/no-such-bundle/verify", "POST")
        results["traversal"] = request(base, "/audit-bundles/..%2F..%2Fetc%2Fpasswd/verify", "POST")
        results["healthz"] = request(base, "/healthz", "GET")
    finally:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=15)
        log.close()

    # The service holds the catalog open while it runs, so the ledger is read once it is down.
    connection = duckdb.connect(str(db_path), read_only=True)
    ledger = connection.execute(
        "SELECT nonce_hex, tenant_id, bundle_id, key_id FROM seal_ledger ORDER BY nonce_hex"
    ).fetchall()
    connection.close()

    yield Workspace(catalog, bundles, results, ledger)


def accepted(workspace, name):
    verdict = workspace.verdict(name)
    return verdict["status"] == "accepted" and verdict["reasons"] == []


def test_healthz(workspace):
    """The service answers /healthz with canonical JSON once it is up."""
    result = workspace.results["healthz"]
    assert result["status"] == 200
    assert result["raw"] == b'{"status":"ok"}\n'
    assert result["content_type"].startswith("application/json")


def test_clean_bundle_is_accepted(workspace):
    """A bundle sealed with a current, allowed, unrevoked key verifies with no reasons."""
    assert accepted(workspace, "clean-quarry"), workspace.verdict("clean-quarry")


def test_second_tenant_with_its_own_allowlist_is_accepted(workspace):
    """A tenant whose catalog allowlist carries the AES-128 suite may seal with it."""
    assert accepted(workspace, "clean-delta-aes128"), workspace.verdict("clean-delta-aes128")


def test_unknown_seal_records_are_ignored(workspace):
    """A seal carrying a record tag the service does not know still verifies."""
    assert accepted(workspace, "clean-unknown-record"), workspace.verdict("clean-unknown-record")


def test_event_table_is_read_from_parquet(workspace):
    """event_count and high_risk_events come from the bundle's Parquet event table."""
    for name in ("clean-quarry", "clean-delta-aes128", "rows-edited"):
        verdict = workspace.verdict(name)
        rows = workspace.bundles[name].rows
        assert verdict["event_count"] == len(rows), name
        assert verdict["high_risk_events"] == high_risk_count(rows), name


def test_archive_digests_are_reported(workspace):
    """content_digest and manifest_digest in the verdict match the archive as shipped."""
    for name in ("clean-quarry", "rows-edited", "manifest-edited"):
        verdict = workspace.verdict(name)
        bundle = workspace.bundles[name]
        assert verdict["content_digest"] == bundle.content_digest, name
        assert verdict["manifest_digest"] == bundle.manifest_digest, name


def test_seal_fields_are_reported(workspace):
    """tenant_id, key_epoch, nonce and sealed_at are read out of the seal footer."""
    for name in ("clean-quarry", "clean-delta-aes128", "revoked-key"):
        verdict = workspace.verdict(name)
        bundle = workspace.bundles[name]
        assert verdict["tenant_id"] == bundle.tenant_id, name
        assert verdict["key_epoch"] == bundle.key_epoch, name
        assert verdict["nonce"] == bundle.nonce_hex, name
        assert verdict["sealed_at"] == iso_ms(bundle.sealed_at_ms), name


def test_revoked_key_is_rejected(workspace):
    """A bundle sealed after its key was revoked is rejected as KEY_REVOKED."""
    assert workspace.reasons("revoked-key") == ["KEY_REVOKED"]


def test_seal_made_before_revocation_still_verifies(workspace):
    """Revocation is not retroactive: a seal predating the revocation instant is accepted."""
    assert accepted(workspace, "before-revocation"), workspace.verdict("before-revocation")


def test_expired_epoch_is_rejected(workspace):
    """A seal made after its epoch's valid_until is rejected as KEY_EPOCH_EXPIRED."""
    assert workspace.reasons("epoch-expired") == ["KEY_EPOCH_EXPIRED"]


def test_epoch_not_yet_valid_is_rejected(workspace):
    """A seal made before its epoch's valid_from is rejected as KEY_EPOCH_NOT_YET_VALID."""
    assert workspace.reasons("epoch-not-yet-valid") == ["KEY_EPOCH_NOT_YET_VALID"]


def test_all_trust_failures_are_reported_together(workspace):
    """A bundle that is both expired and revoked reports both reasons, sorted."""
    assert workspace.reasons("expired-and-revoked") == ["KEY_EPOCH_EXPIRED", "KEY_REVOKED"]


def test_algorithm_outside_tenant_allowlist_is_rejected(workspace):
    """A suite the service supports but the tenant is not allowed to use is rejected."""
    assert workspace.reasons("algorithm-not-allowed") == ["ALGORITHM_NOT_ALLOWED"]


def test_unsupported_algorithm_is_rejected(workspace):
    """A suite the service cannot open at all is rejected as UNSUPPORTED_ALGORITHM."""
    assert workspace.reasons("unsupported-algorithm") == ["UNSUPPORTED_ALGORITHM"]


def test_suspended_tenant_is_rejected(workspace):
    """A tenant whose catalog status is not active is rejected as TENANT_SUSPENDED."""
    assert workspace.reasons("tenant-suspended") == ["TENANT_SUSPENDED"]


def test_unknown_tenant_is_rejected_on_its_own(workspace):
    """A tenant absent from the catalog is rejected as UNKNOWN_TENANT and nothing else."""
    assert workspace.reasons("unknown-tenant") == ["UNKNOWN_TENANT"]


def test_unknown_key_epoch_is_rejected(workspace):
    """An epoch the catalog does not carry is rejected as UNKNOWN_KEY_EPOCH."""
    assert workspace.reasons("unknown-epoch") == ["UNKNOWN_KEY_EPOCH"]


def test_key_id_mismatch_is_rejected(workspace):
    """A seal naming a key id the catalog does not hold for that epoch is rejected."""
    assert workspace.reasons("key-id-mismatch") == ["KEY_ID_MISMATCH"]


def test_edited_event_rows_are_detected(workspace):
    """Editing an event row after sealing breaks the sealed content digest."""
    assert workspace.reasons("rows-edited") == ["EVENT_CONTENT_MISMATCH"]


def test_dropped_event_row_is_detected(workspace):
    """Dropping a row breaks both the sealed row count and the sealed content digest."""
    assert workspace.reasons("row-dropped") == ["EVENT_CONTENT_MISMATCH", "EVENT_COUNT_MISMATCH"]


def test_edited_manifest_is_detected(workspace):
    """Editing the manifest after sealing breaks the sealed manifest digest."""
    assert workspace.reasons("manifest-edited") == ["MANIFEST_DIGEST_MISMATCH"]


def test_payload_sealed_with_the_wrong_key_is_rejected(workspace):
    """A payload encrypted under another epoch's key does not authenticate."""
    assert workspace.reasons("payload-wrong-key") == ["SEAL_PAYLOAD_UNDECRYPTABLE"]


def test_flipped_ciphertext_breaks_the_mac(workspace):
    """A footer byte flipped under a repaired CRC fails both the MAC and the payload."""
    assert workspace.reasons("ciphertext-flipped") == ["SEAL_HMAC_INVALID", "SEAL_PAYLOAD_UNDECRYPTABLE"]


def test_crc_mismatch_short_circuits(workspace):
    """A footer whose transport CRC is wrong is rejected on the CRC alone, MAC or not."""
    assert workspace.reasons("crc-flipped") == ["SEAL_CRC_MISMATCH"]


def test_legacy_v1_seal_is_not_accepted(workspace):
    """v1 bundles were migrated out; a v1 footer is MALFORMED_SEAL, not a verdict."""
    verdict = workspace.verdict("legacy-v1")
    assert verdict["reasons"] == ["MALFORMED_SEAL"]
    assert verdict["tenant_id"] is None
    assert verdict["nonce"] is None


def test_unreadable_archive_is_rejected(workspace):
    """Bytes that are not a tar at all are rejected as MALFORMED_ARCHIVE with null evidence."""
    verdict = workspace.verdict("garbage")
    assert verdict["reasons"] == ["MALFORMED_ARCHIVE"]
    assert verdict["event_count"] is None
    assert verdict["content_digest"] is None


def test_archive_missing_a_member_is_rejected(workspace):
    """An archive that carries no seal member at all is MALFORMED_ARCHIVE."""
    assert workspace.reasons("seal-missing") == ["MALFORMED_ARCHIVE"]


def test_archive_with_an_unreadable_event_table_is_rejected(workspace):
    """An archive whose Parquet member is not Parquet is MALFORMED_ARCHIVE, not a crash."""
    verdict = workspace.verdict("events-unreadable")
    assert verdict["reasons"] == ["MALFORMED_ARCHIVE"]
    assert verdict["event_count"] is None


def test_archive_evidence_survives_a_bad_seal(workspace):
    """The event table is still summarised when the seal itself is unusable."""
    verdict = workspace.verdict("crc-flipped")
    bundle = workspace.bundles["crc-flipped"]
    assert verdict["event_count"] == len(bundle.rows)
    assert verdict["content_digest"] == bundle.content_digest


def test_replayed_seal_is_rejected(workspace):
    """A bundle that was already accepted is rejected as SEAL_REPLAYED on resubmission."""
    assert workspace.results["clean-quarry-again"]["body"]["reasons"] == ["SEAL_REPLAYED"]


def test_accepted_seals_are_written_to_the_ledger(workspace):
    """Every accepted bundle, and only those, leaves one row in the catalog's seal_ledger."""
    expected = {
        workspace.bundles[name].nonce_hex: (workspace.bundles[name].tenant_id, name)
        for name in ("clean-quarry", "clean-delta-aes128", "clean-unknown-record", "before-revocation")
    }
    assert len(workspace.ledger) == len(expected), workspace.ledger
    for nonce_hex, tenant_id, bundle_id, key_id in workspace.ledger:
        assert nonce_hex in expected
        assert (tenant_id, bundle_id) == expected[nonce_hex]
        assert key_id != ""


def test_rejected_bundles_leave_no_trace(workspace):
    """A rejected bundle writes nothing back, and stays rejected the same way on resubmission."""
    rejected_nonces = {
        workspace.bundles[name].nonce_hex
        for name in ("revoked-key", "rows-edited", "crc-flipped", "key-id-mismatch")
    }
    ledger_nonces = {row[0] for row in workspace.ledger}
    assert rejected_nonces.isdisjoint(ledger_nonces)
    assert workspace.results["rows-edited-again"]["raw"] == workspace.results["rows-edited"]["raw"]


def test_missing_bundle_is_404(workspace):
    """A bundle id with no archive on disk is a 404, not a verdict."""
    result = workspace.results["missing"]
    assert result["status"] == 404
    assert result["body"] == {"error": "bundle_not_found"}


def test_bundle_id_is_validated(workspace):
    """A bundle id that could escape the bundle directory is refused."""
    result = workspace.results["traversal"]
    assert result["status"] == 400
    assert result["body"] == {"error": "invalid_bundle_id"}


def test_verdict_is_canonical_json(workspace):
    """Verdict bodies are compact, key-sorted JSON with exactly one trailing newline."""
    raw = workspace.results["clean-quarry"]["raw"]
    assert raw.endswith(b"\n") and not raw[:-1].endswith(b"\n")
    assert raw.decode("utf-8") == canonical_json(json.loads(raw)) + "\n"
    assert workspace.results["clean-quarry"]["content_type"].startswith("application/json")


def test_evidence_digest_commits_to_the_verdict(workspace):
    """evidence_digest is the SHA-256 of the canonical verdict with that field removed."""
    for name in ("clean-quarry", "revoked-key", "garbage", "legacy-v1"):
        verdict = dict(workspace.verdict(name))
        digest = verdict.pop("evidence_digest")
        preimage = (canonical_json(verdict) + "\n").encode("utf-8")
        assert digest == hashlib.sha256(preimage).hexdigest(), name
