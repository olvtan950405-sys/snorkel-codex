"""Black-box verification for RepoGuard's repository reconciliation contract."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest

APP = Path("/app")
BIN = APP / "bin" / "repoguard"


def canonical(value: object) -> bytes:
    """Return the contract's canonical JSON file encoding."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


@pytest.fixture(scope="session")
def pristine(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Capture the repository and state once, independently of per-test mutations."""
    root = tmp_path_factory.mktemp("pristine")
    shutil.copytree(APP / "repository", root / "repository")
    shutil.copytree(APP / "state", root / "state")
    return root


@pytest.fixture
def workspace(pristine: Path, tmp_path: Path) -> tuple[Path, Path, Path]:
    """Provide isolated repository, state, and output trees for each test."""
    repository = tmp_path / "repository"
    state = tmp_path / "state"
    out = tmp_path / "out"
    shutil.copytree(pristine / "repository", repository)
    shutil.copytree(pristine / "state", state)
    return repository, state, out


def run_guard(repository: Path, state: Path, out: Path) -> subprocess.CompletedProcess[str]:
    """Run RepoGuard against explicitly supplied paths without relying on defaults."""
    env = os.environ.copy()
    env.update(
        REPOGUARD_REPOSITORY=str(repository),
        REPOGUARD_TRUSTED_ROOT=str(state / "trusted-root.json"),
        REPOGUARD_STATE_DB=str(state / "trust.db"),
        REPOGUARD_OUT=str(out),
    )
    return subprocess.run([str(BIN), "reconcile"], env=env, capture_output=True, text=True, timeout=90)


def read_report(out: Path) -> dict:
    """Load a produced report as JSON."""
    return json.loads((out / "report.json").read_text())


def state_rows(database: Path) -> list[tuple[str, int]]:
    """Read monotonic state in stable order."""
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT role,version FROM accepted ORDER BY role").fetchall()


def public_from_seed(seed_hex: str) -> str:
    """Derive an Ed25519 raw public key from a deterministic PKCS#8 seed."""
    private_der = bytes.fromhex("302e020100300506032b657004220420" + seed_hex)
    with tempfile.TemporaryDirectory() as directory:
        private = Path(directory) / "private.der"
        public = Path(directory) / "public.der"
        private.write_bytes(private_der)
        subprocess.run(
            ["openssl", "pkey", "-in", str(private), "-inform", "DER", "-pubout", "-outform", "DER", "-out", str(public)],
            check=True,
            capture_output=True,
        )
        return public.read_bytes()[-32:].hex()


def test_development_repository_exercises_all_target_verdicts(workspace):
    """The shipped repository yields the independently expected verdict for every target."""
    repository, state, out = workspace
    result = run_guard(repository, state, out)
    assert result.returncode == 0, result.stderr
    report = read_report(out)
    assert report["metadata_versions"] == {
        "plugins": 4,
        "private": 3,
        "root": 2,
        "snapshot": 12,
        "targets": 7,
        "timestamp": 19,
    }
    entries = {item["path"]: item for item in report["targets"]}
    assert {path: item["status"] for path, item in entries.items()} == {
        "bin/api-v2.4.tar": "trusted",
        "bin/legacy.tar": "quarantined",
        "bin/missing-debug.tar": "regenerate",
        "misc/orphan.txt": "quarantined",
        "plugins/acme.zip": "trusted",
        "plugins/private/ops.zip": "quarantined",
    }
    assert entries["bin/legacy.tar"]["reason"] == "target_mismatch"
    assert entries["bin/missing-debug.tar"]["reason"] == "target_missing"
    assert entries["misc/orphan.txt"]["reason"] == "unclaimed_target"


def test_terminating_delegation_prevents_broader_fallback(workspace):
    """A matching terminating role blocks a descriptor in the later broad plugin role."""
    repository, state, out = workspace
    assert run_guard(repository, state, out).returncode == 0
    entry = next(item for item in read_report(out)["targets"] if item["path"] == "plugins/private/ops.zip")
    assert entry["status"] == "quarantined"
    assert entry["reason"] == "unclaimed_target"
    assert entry["role"] is None


def test_report_and_per_target_files_are_canonical(workspace):
    """Reports and enforcement records use compact sorted JSON with one final newline."""
    repository, state, out = workspace
    assert run_guard(repository, state, out).returncode == 0
    report = read_report(out)
    assert (out / "report.json").read_bytes() == canonical(report)
    for entry in report["targets"]:
        folder = {"trusted": "authorizations", "quarantined": "quarantine", "regenerate": "regeneration"}[entry["status"]]
        artifact = out / folder / (entry["path"].replace("/", "__") + ".json")
        assert artifact.read_bytes() == canonical(entry)


def test_actual_target_facts_are_derived_from_bytes(workspace):
    """Actual length and digest in a mismatch verdict describe current target bytes."""
    repository, state, out = workspace
    target = repository / "targets" / "bin" / "legacy.tar"
    assert run_guard(repository, state, out).returncode == 0
    entry = next(item for item in read_report(out)["targets"] if item["path"] == "bin/legacy.tar")
    assert entry["length"] == target.stat().st_size
    assert entry["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()


def test_fresh_unclaimed_file_is_discovered_dynamically(workspace):
    """A newly introduced path is reconciled from the filesystem rather than a fixture list."""
    repository, state, out = workspace
    body = b"fresh target unknown to the shipped metadata\n"
    name = f"generated/{hashlib.sha256(body).hexdigest()[:13]}.bin"
    target = repository / "targets" / name
    target.parent.mkdir(parents=True)
    target.write_bytes(body)
    assert run_guard(repository, state, out).returncode == 0
    entry = next(item for item in read_report(out)["targets"] if item["path"] == name)
    assert entry == {
        "length": len(body),
        "path": name,
        "reason": "unclaimed_target",
        "role": None,
        "sha256": hashlib.sha256(body).hexdigest(),
        "status": "quarantined",
    }


def test_semantic_target_change_changes_its_verdict(workspace):
    """Changing authenticated target bytes converts trust to a derived mismatch verdict."""
    repository, state, out = workspace
    target = repository / "targets" / "bin" / "api-v2.4.tar"
    target.write_bytes(b"replacement bytes created by verifier\n")
    assert run_guard(repository, state, out).returncode == 0
    entry = next(item for item in read_report(out)["targets"] if item["path"] == "bin/api-v2.4.tar")
    assert entry["status"] == "quarantined"
    assert entry["reason"] == "target_mismatch"
    assert entry["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()


def test_duplicate_signatures_do_not_satisfy_a_threshold(workspace):
    """Two copies of one authorized signature cannot meet the two-key targets threshold."""
    repository, state, out = workspace
    metadata = repository / "metadata" / "targets.json"
    document = json.loads(metadata.read_text())
    document["signatures"][1] = dict(document["signatures"][0])
    metadata.write_bytes(canonical(document))
    before_rows = state_rows(state / "trust.db")
    before_root = (state / "trusted-root.json").read_bytes()
    result = run_guard(repository, state, out)
    assert result.returncode == 2
    assert read_report(out)["repository_status"] == "invalid"
    assert state_rows(state / "trust.db") == before_rows
    assert (state / "trusted-root.json").read_bytes() == before_root


def test_rotation_requires_the_old_root_threshold(workspace):
    """A candidate self-signed by its new quorum is rejected without the old-root quorum."""
    repository, state, out = workspace
    old_signed = {
        "_type": "root",
        "expires": "2028-01-01T00:00:00Z",
        "keys": {
            "old-a": {"keytype": "ed25519", "public": public_from_seed("01" * 32), "scheme": "ed25519"},
            "old-b": {"keytype": "ed25519", "public": public_from_seed("02" * 32), "scheme": "ed25519"},
        },
        "roles": {"root": {"keyids": ["old-a", "old-b"], "threshold": 2}},
        "version": 1,
    }
    (state / "trusted-root.json").write_bytes(canonical({"signatures": [], "signed": old_signed}))
    with sqlite3.connect(state / "trust.db") as connection:
        connection.execute("UPDATE accepted SET version=1 WHERE role='root'")
        connection.commit()
    candidate = repository / "metadata" / "root.json"
    document = json.loads(candidate.read_text())
    document["signatures"] = [item for item in document["signatures"] if item["keyid"].startswith("root-")]
    candidate.write_bytes(canonical(document))
    before = state_rows(state / "trust.db")
    before_root = (state / "trusted-root.json").read_bytes()
    result = run_guard(repository, state, out)
    assert result.returncode == 2
    assert result.stderr == "repoguard: old_root_threshold\n"
    assert read_report(out) == {
        "reason": "old_root_threshold",
        "repository_status": "invalid",
        "targets": [],
    }
    assert state_rows(state / "trust.db") == before
    assert (state / "trusted-root.json").read_bytes() == before_root


def test_timestamp_commits_to_snapshot_length(workspace):
    """A snapshot with unchanged JSON meaning but changed stored length is rejected."""
    repository, state, out = workspace
    snapshot = repository / "metadata" / "snapshot.json"
    snapshot.write_bytes(snapshot.read_bytes() + b" ")
    before = state_rows(state / "trust.db")
    result = run_guard(repository, state, out)
    assert result.returncode == 2
    assert state_rows(state / "trust.db") == before


def test_rollback_is_rejected_without_advancing_any_role(workspace):
    """Persisted versions are monotonic and a single rolled-back role leaves all state unchanged."""
    repository, state, out = workspace
    with sqlite3.connect(state / "trust.db") as connection:
        connection.execute("UPDATE accepted SET version=version+20 WHERE role='snapshot'")
        connection.commit()
    before = state_rows(state / "trust.db")
    before_root = (state / "trusted-root.json").read_bytes()
    result = run_guard(repository, state, out)
    assert result.returncode == 2
    assert result.stderr == "repoguard: rollback:snapshot\n"
    assert read_report(out) == {
        "reason": "rollback:snapshot",
        "repository_status": "invalid",
        "targets": [],
    }
    assert state_rows(state / "trust.db") == before
    assert (state / "trusted-root.json").read_bytes() == before_root


def test_invalid_signature_does_not_advance_state(workspace):
    """A cryptographically invalid timestamp signature fails before any persistent write."""
    repository, state, out = workspace
    timestamp = repository / "metadata" / "timestamp.json"
    document = json.loads(timestamp.read_text())
    document["signatures"][0]["sig"] = "00" * 64
    timestamp.write_bytes(canonical(document))
    before_rows = state_rows(state / "trust.db")
    before_root = (state / "trusted-root.json").read_bytes()
    assert run_guard(repository, state, out).returncode == 2
    assert state_rows(state / "trust.db") == before_rows
    assert (state / "trusted-root.json").read_bytes() == before_root


def test_equal_versions_make_reconciliation_idempotent(workspace):
    """Running twice with accepted versions and the same trusted root is valid and byte-identical."""
    repository, state, out = workspace
    first = run_guard(repository, state, out)
    assert first.returncode == 0, first.stderr
    snapshot = {path.relative_to(out).as_posix(): path.read_bytes() for path in out.rglob("*") if path.is_file()}
    rows = state_rows(state / "trust.db")
    second = run_guard(repository, state, out)
    assert second.returncode == 0, second.stderr
    assert {path.relative_to(out).as_posix(): path.read_bytes() for path in out.rglob("*") if path.is_file()} == snapshot
    assert state_rows(state / "trust.db") == rows


def test_stale_artifacts_are_removed_on_failure(workspace):
    """A failed run replaces prior output with only its canonical invalid report."""
    repository, state, out = workspace
    assert run_guard(repository, state, out).returncode == 0
    timestamp = repository / "metadata" / "timestamp.json"
    document = json.loads(timestamp.read_text())
    document["signatures"][0]["sig"] = "ff" * 64
    timestamp.write_bytes(canonical(document))
    assert run_guard(repository, state, out).returncode == 2
    assert sorted(path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()) == ["report.json"]
    report = read_report(out)
    assert (out / "report.json").read_bytes() == canonical(report)


def test_audit_is_derived_in_report_order(workspace):
    """The Markdown audit contains one stable line per report target in matching order."""
    repository, state, out = workspace
    assert run_guard(repository, state, out).returncode == 0
    report = read_report(out)
    lines = ["# Repository reconciliation", ""]
    for entry in report["targets"]:
        detail = entry["reason"] if entry["reason"] is not None else entry["role"]
        lines.append(f"- `{entry['path']}`: {entry['status']} ({detail})")
    assert (out / "audit.md").read_text() == "\n".join(lines) + "\n"


def test_default_paths_and_cli_contract(tmp_path: Path):
    """The documented default invocation works and unsupported commands are rejected."""
    result = subprocess.run([str(BIN), "not-a-command"], capture_output=True, text=True)
    assert result.returncode == 64
    assert "usage:" in result.stderr
    default = subprocess.run([str(BIN), "reconcile"], capture_output=True, text=True, timeout=90)
    assert default.returncode == 0, default.stderr
    assert (APP / "out" / "report.json").exists()
