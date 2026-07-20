"""Behavioral tests for the GlacierVault quorum verifier."""

from __future__ import annotations

import concurrent.futures
import sqlite3
import subprocess

import pytest

from bundlekit import APP, build_case, run_guard


@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("noncanonical", "manifest_noncanonical"),
        ("segment", "segment_invalid"),
        ("merkle", "merkle_mismatch"),
        ("tenant_unknown", "tenant_unknown"),
    ],
)
def test_manifest_and_content_failures_follow_precedence(tmp_path, case, status):
    """Canonical encoding, streamed content, Merkle, and tenant failures get exact verdicts."""
    bundle, catalog = build_case(tmp_path, case)
    verdict = run_guard(bundle, catalog, tmp_path / "out.json")
    assert verdict["status"] == status
    assert verdict["signers"] == []


@pytest.mark.parametrize(
    ("case", "status"),
    [("quorum", "quorum_not_met"), ("invalid_signature", "signature_invalid"), ("revoked", "key_untrusted")],
)
def test_signature_trust_and_quorum_are_independent(tmp_path, case, status):
    """Invalid cryptography, temporal trust, and each quorum threshold are separately enforced."""
    bundle, catalog = build_case(tmp_path, case)
    assert run_guard(bundle, catalog, tmp_path / "out.json")["status"] == status


def test_matching_emergency_exception_is_narrow_but_effective(tmp_path):
    """A matching exception waives key time status while retaining signature and quorum checks."""
    bundle, catalog = build_case(tmp_path, "exception")
    verdict = run_guard(bundle, catalog, tmp_path / "out.json")
    assert verdict["status"] == "accepted"
    assert verdict["signers"] == ["op-1", "rec-1"]


def test_acceptance_output_and_replay_ledger(tmp_path):
    """Acceptance emits the exact schema and atomically records a replay-protection row."""
    bundle, catalog = build_case(tmp_path)
    first = run_guard(bundle, catalog, tmp_path / "first.json")
    second = run_guard(bundle, catalog, tmp_path / "second.json")
    assert list(first) == ["bundle_id", "manifest_digest", "nonce", "signers", "status", "tenant"]
    assert first["status"] == "accepted" and second["status"] == "replayed"
    with sqlite3.connect(catalog) as connection:
        assert connection.execute("SELECT count(*) FROM accepted_nonces").fetchone()[0] == 1


def test_concurrent_replay_claim_has_one_winner(tmp_path):
    """Two concurrent claims for one nonce produce exactly one acceptance and one replay."""
    bundle, catalog = build_case(tmp_path)
    subprocess.run(["go", "build", "-o", APP / "bin/backupguard", "./cmd/backupguard"], cwd=APP, check=True)

    def invoke(index: int) -> str:
        output = tmp_path / f"race-{index}.json"
        return run_guard(bundle, catalog, output, build=False)["status"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(invoke, range(2)))
    assert sorted(statuses) == ["accepted", "replayed"]
