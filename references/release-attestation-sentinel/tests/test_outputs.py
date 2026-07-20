"""Behavioural verifier for the ReleaseSentinel worker.

Every run mints fresh Ed25519-signed badges and builds a fresh git repository, then compares the
worker's snapshot against an independent reference implementation of the trust policy.  Because the
signing keys and the expected snapshot are computed at test time, a submission cannot pass by
emitting a hardcoded answer.  The native extractor is additionally exercised under Valgrind so a
memory-unsafe or truncating implementation fails regardless of the Java layer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import reference_policy as rp  # noqa: E402
import sentinel_kit as kit  # noqa: E402

APP = Path("/app")
JAR = APP / "build" / "sentinel.jar"
NATIVE_LIB = APP / "build" / "libattest.so"
SHIPPED_BADGES = APP / "fixtures" / "badges"
SHIPPED_KEYRING = APP / "config" / "keyring.json"
SHIPPED_REPO = APP / "repo"

SEEDS = {
    name: bytes.fromhex(value)
    for name, value in json.loads((Path(__file__).parent / "signing_keys.json").read_text()).items()
}

CHANGELOG = """# Changelog

## v8.5.0 (release/8.5)

- search-api: incremental index rebuilds

## v8.4.1 (hotfix/8.4.1)

- payments-api: fix double capture

## v8.4.0 (release/8.4)

- orders-api: partial fulfilment

## v8.3.4 (release/8.3)

- search-api: relevance tuning

## v8.2.1 (release/8.2)

- orders-api: tax rounding
"""

TAG_BRANCHES = [
    ("v8.2.1", "release/8.2"),
    ("v8.3.4", "release/8.3"),
    ("v8.4.0", "release/8.4"),
    ("v8.4.1", "hotfix/8.4.1"),
    ("v8.5.0", "release/8.5"),
]


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------


def statement(**overrides):
    base = {
        "artifact_digest": "sha256:" + "a" * 64,
        "issued_at": "2026-05-12T09:14:00.000Z",
        "key_id": "k-build-2026a",
        "release_branch": "release/8.4",
        "release_tag": "v8.4.0",
        "service": "payments-api",
    }
    base.update(overrides)
    return base


def mint_badge(directory: Path, name: str, stmt: dict, *, sign_as: str | None = None,
               segments: int = 2, corrupt_crc: bool = False, omit: bool = False,
               tamper: dict | None = None) -> None:
    seed = SEEDS[sign_as if sign_as is not None else stmt["key_id"]]
    attestation = kit.build_attestation(stmt, seed)
    if tamper is not None:
        attestation["statement"] = dict(stmt, **tamper)
    payload = kit.canonical_json(attestation)
    png = kit.build_badge_png(payload, segments=segments, corrupt_crc=corrupt_crc, omit_payload=omit)
    (directory / name).write_bytes(png)


def build_repo(root: Path) -> None:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
        GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00",
    )
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True, env=env)
    (root / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True, env=env)
    for tag, _branch in TAG_BRANCHES:
        subprocess.run(["git", "-C", str(root), "tag", tag], check=True, env=env)


def write_keyring(path: Path, key_ids: list[str]) -> None:
    import base64

    keys = [
        {
            "key_id": key_id,
            "public_key": base64.b64encode(kit.spki_der(kit.public_key(SEEDS[key_id]))).decode("ascii"),
        }
        for key_id in sorted(key_ids)
    ]
    path.write_text(json.dumps({"keys": keys}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_worker(badge_dir: Path, repo_dir: Path, keyring: Path, out: Path) -> dict:
    result = subprocess.run(
        [
            "java", f"-Djava.library.path={APP / 'build'}", "-jar", str(JAR),
            "snapshot", "--badges", str(badge_dir), "--repo", str(repo_dir),
            "--keyring", str(keyring), "--out", str(out),
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"worker exited {result.returncode}: {result.stderr}"
    raw = out.read_bytes()
    assert raw.endswith(b"\n"), "snapshot must end with exactly one trailing newline"
    assert not raw[:-1].endswith(b"\n"), "snapshot must end with exactly one trailing newline"
    return json.loads(raw)


@pytest.fixture()
def workspace(tmp_path):
    badges = tmp_path / "badges"
    badges.mkdir()
    repo = tmp_path / "repo"
    build_repo(repo)
    keyring = tmp_path / "keyring.json"
    write_keyring(keyring, ["k-build-2026a", "k-build-2025b", "k-legacy-2024", "k-ci-sandbox"])
    out = tmp_path / "snapshot.json"
    return badges, repo, keyring, out


# --------------------------------------------------------------------------------------------
# artefacts exist
# --------------------------------------------------------------------------------------------


def test_worker_artifacts_are_built():
    """The build produces both the runnable worker jar and the native extractor library."""
    assert JAR.is_file(), "expected /app/build/sentinel.jar to be built"
    assert NATIVE_LIB.is_file(), "expected /app/build/libattest.so to be built"


# --------------------------------------------------------------------------------------------
# end-to-end over the shipped fixtures
# --------------------------------------------------------------------------------------------


def test_shipped_fixtures_match_reference_snapshot(tmp_path):
    """The worker's snapshot over the shipped badges equals the independent reference snapshot."""
    out = tmp_path / "snapshot.json"
    produced = run_worker(SHIPPED_BADGES, SHIPPED_REPO, SHIPPED_KEYRING, out)
    expected = rp.build_snapshot(SHIPPED_BADGES, SHIPPED_REPO, SHIPPED_KEYRING)
    assert produced == expected


def test_shipped_fixtures_cover_every_status(tmp_path):
    """The shipped fixtures exercise all seven verdicts, so a partial worker cannot pass by luck."""
    out = tmp_path / "snapshot.json"
    produced = run_worker(SHIPPED_BADGES, SHIPPED_REPO, SHIPPED_KEYRING, out)
    seen = {badge["status"] for badge in produced["badges"]}
    assert seen == set(rp.STATUS_ORDER)


# --------------------------------------------------------------------------------------------
# per-rule verdicts on freshly minted badges
# --------------------------------------------------------------------------------------------

RULE_CASES = [
    ("accepted", dict(), {}),
    ("accepted_hotfix", dict(release_tag="v8.4.1", release_branch="release/8.4"), {}),
    ("branch_conflict", dict(release_branch="release/9.0"), {}),
    ("tag_unknown", dict(release_tag="v9.9.9"), {}),
    ("key_untrusted_absent", dict(key_id="k-forge"), {}),
    ("key_untrusted_sandbox", dict(key_id="k-ci-sandbox"), {}),
    ("legacy_pre_revocation", dict(key_id="k-legacy-2024", service="search-api",
                                   issued_at="2026-03-30T00:00:00.000Z",
                                   release_tag="v8.2.1", release_branch="release/8.2"), {}),
    ("legacy_revoked", dict(key_id="k-legacy-2024", service="search-api",
                            issued_at="2026-05-20T00:00:00.000Z",
                            release_tag="v8.3.4", release_branch="release/8.3"), {}),
    ("legacy_exception", dict(key_id="k-legacy-2024", service="payments-api",
                              issued_at="2026-05-20T00:00:00.000Z",
                              release_tag="v8.3.4", release_branch="release/8.3"), {}),
    ("rotation_intime", dict(key_id="k-build-2025b", service="orders-api",
                             issued_at="2026-04-11T00:00:00.000Z",
                             release_tag="v8.2.1", release_branch="release/8.2"), {}),
    ("rotation_late", dict(key_id="k-build-2025b", service="orders-api",
                           issued_at="2026-05-06T00:00:00.000Z",
                           release_tag="v8.4.0", release_branch="release/8.4"), {}),
]


@pytest.mark.parametrize("label,overrides,_extra", RULE_CASES)
def test_single_rule_verdicts(workspace, label, overrides, _extra):
    """Each freshly minted badge receives exactly the verdict the reconstructed policy requires."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, f"{label}.png", statement(**overrides))
    produced = run_worker(badges, repo, keyring, out)
    expected = rp.build_snapshot(badges, repo, keyring)
    assert produced == expected


def test_tampered_statement_is_signature_invalid(workspace):
    """A badge whose statement was altered after signing is rejected as an invalid signature."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "tampered.png", statement(), tamper={"release_tag": "v8.5.0"})
    produced = run_worker(badges, repo, keyring, out)
    entry = produced["badges"][0]
    assert entry["status"] == "signature_invalid"
    assert produced == rp.build_snapshot(badges, repo, keyring)


def test_sandbox_key_is_untrusted_not_a_bad_signature(workspace):
    """A perfectly signed badge from the sandbox key is untrusted, distinct from a bad signature."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "sandbox.png", statement(key_id="k-ci-sandbox", service="orders-api"))
    produced = run_worker(badges, repo, keyring, out)
    assert produced["badges"][0]["status"] == "key_untrusted"


# --------------------------------------------------------------------------------------------
# precedence and boundary behaviour
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("issued_at,expected", [
    ("2026-04-02T17:29:59.999Z", "accepted"),
    ("2026-04-02T17:30:00.000Z", "key_revoked"),
])
def test_legacy_revocation_boundary_is_inclusive_on_reject(workspace, issued_at, expected):
    """The legacy key's revocation cutoff rejects a statement issued at the exact instant."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "legacy.png",
               statement(key_id="k-legacy-2024", service="search-api", issued_at=issued_at,
                         release_tag="v8.3.4", release_branch="release/8.3"))
    produced = run_worker(badges, repo, keyring, out)
    assert produced["badges"][0]["status"] == expected


@pytest.mark.parametrize("issued_at,expected", [
    ("2026-04-30T23:59:59.999Z", "accepted"),
    ("2026-05-01T00:00:00.000Z", "key_revoked"),
])
def test_previous_build_key_retirement_boundary(workspace, issued_at, expected):
    """The previous build key is honoured until its cutover instant, and retired from it on."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "rotation.png",
               statement(key_id="k-build-2025b", service="orders-api", issued_at=issued_at,
                         release_tag="v8.2.1", release_branch="release/8.2"))
    assert run_worker(badges, repo, keyring, out)["badges"][0]["status"] == expected


@pytest.mark.parametrize("issued_at,expected_status,expected_exception", [
    ("2026-06-29T23:59:59.999Z", "accepted", "EX-14"),
    ("2026-06-30T00:00:00.000Z", "key_revoked", None),
])
def test_payments_exception_expiry_boundary(workspace, issued_at, expected_status, expected_exception):
    """The payments-api legacy exception lapses at its expiry instant and is not resurrected."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "exception.png",
               statement(key_id="k-legacy-2024", service="payments-api", issued_at=issued_at,
                         release_tag="v8.5.0", release_branch="release/8.5"))
    entry = run_worker(badges, repo, keyring, out)["badges"][0]
    assert entry["status"] == expected_status
    assert entry["exception_id"] == expected_exception


def test_exception_is_scoped_to_payments_only(workspace):
    """The legacy exception does not extend to another service issued in the same window."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "search.png",
               statement(key_id="k-legacy-2024", service="search-api",
                         issued_at="2026-05-20T00:00:00.000Z",
                         release_tag="v8.3.4", release_branch="release/8.3"))
    assert run_worker(badges, repo, keyring, out)["badges"][0]["status"] == "key_revoked"


def test_untrusted_key_precedes_signature_check(workspace):
    """An untrusted key id is reported before any signature verification is attempted."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "forge.png", statement(key_id="k-forge"), tamper={"service": "orders-api"})
    assert run_worker(badges, repo, keyring, out)["badges"][0]["status"] == "key_untrusted"


def test_changelog_branch_overrides_claimed_branch_on_accept(workspace):
    """An accepted badge records the branch named by the changelog, not the badge's own claim."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "hotfix.png", statement(release_tag="v8.4.1", release_branch="release/8.4"))
    entry = run_worker(badges, repo, keyring, out)["badges"][0]
    assert entry["status"] == "accepted"
    assert entry["release_branch"] == "hotfix/8.4.1"


# --------------------------------------------------------------------------------------------
# determinism and digest
# --------------------------------------------------------------------------------------------


def test_digest_is_sha256_of_canonical_badge_array(workspace):
    """The snapshot digest is the SHA-256 of the canonical bytes of the badge array."""
    badges, repo, keyring, out = workspace
    for index, (label, overrides, _extra) in enumerate(RULE_CASES):
        mint_badge(badges, f"{index:02d}-{label}.png", statement(**overrides))
    produced = run_worker(badges, repo, keyring, out)
    recomputed = kit.sha256_hex(kit.canonical_json(produced["badges"]))
    assert produced["digest"] == recomputed


def test_counts_include_zero_valued_statuses(workspace):
    """The counts object always carries every status key, including those with a count of zero."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "one.png", statement())
    counts = run_worker(badges, repo, keyring, out)["counts"]
    assert set(counts) == set(rp.STATUS_ORDER)
    assert counts["accepted"] == 1
    assert counts["tag_unknown"] == 0


def test_input_formatting_does_not_change_the_snapshot(workspace):
    """Reordering statement keys and reflowing the payload leaves the snapshot bytes unchanged."""
    badges, repo, keyring, out = workspace
    stmt = statement()
    mint_badge(badges, "canonical.png", stmt)
    first = out.parent / "first.json"
    run_worker(badges, repo, keyring, first)
    baseline = first.read_bytes()

    # Rebuild the same badge from a differently serialised, semantically identical payload.
    import base64

    signature = base64.b64encode(kit.sign(SEEDS[stmt["key_id"]], kit.canonical_json(stmt))).decode()
    noisy = json.dumps({"statement": stmt, "signature": signature}, indent=4).encode("utf-8")
    (badges / "canonical.png").write_bytes(kit.build_badge_png(noisy, segments=3))
    second = out.parent / "second.json"
    run_worker(badges, repo, keyring, second)
    assert second.read_bytes() == baseline


def test_semantic_change_changes_the_digest(workspace):
    """A change to a badge's meaning changes the snapshot digest."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "badge.png", statement(release_tag="v8.4.0", release_branch="release/8.4"))
    before = run_worker(badges, repo, keyring, out)["digest"]

    (badges / "badge.png").unlink()
    mint_badge(badges, "badge.png", statement(release_tag="v8.4.0", release_branch="release/9.0"))
    after = run_worker(badges, repo, keyring, out)["digest"]
    assert before != after


def test_unreadable_badges_carry_null_fields(workspace):
    """A badge with a corrupt attestation chunk is unreadable with null descriptive fields."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "crc.png", statement(), corrupt_crc=True)
    mint_badge(badges, "empty.png", statement(), omit=True)
    produced = run_worker(badges, repo, keyring, out)
    for entry in produced["badges"]:
        assert entry["status"] == "badge_unreadable"
        assert entry["key_id"] is None
        assert entry["release_branch"] is None


def _write_raw_badge(directory: Path, name: str, payload: bytes, segments: int = 2) -> None:
    (directory / name).write_bytes(kit.build_badge_png(payload, segments=segments))


MALFORMED_PAYLOADS = {
    "not_json": b"this is not json at all",
    "truncated_json": b'{"signature":"abc","statement":{"key_id":',
    "json_array": b'[{"signature":"a"},{"statement":{}}]',
    "invalid_utf8": b'{"signature":"a","statement":"\xff\xfe"}',
    "empty_payload": b"",
}


@pytest.mark.parametrize("label", sorted(MALFORMED_PAYLOADS))
def test_malformed_payloads_are_unreadable(workspace, label):
    """A payload that is not valid UTF-8 JSON is reported as an unreadable badge."""
    badges, repo, keyring, out = workspace
    _write_raw_badge(badges, f"{label}.png", MALFORMED_PAYLOADS[label])
    entry = run_worker(badges, repo, keyring, out)["badges"][0]
    assert entry["status"] == "badge_unreadable"
    assert entry["service"] is None


def _signed_payload(stmt: dict, mutate) -> bytes:
    """Sign ``stmt`` honestly, then apply ``mutate`` to the attestation document."""
    attestation = kit.build_attestation(stmt, SEEDS[stmt["key_id"]])
    mutate(attestation)
    return kit.canonical_json(attestation)


SHAPE_VIOLATIONS = {
    "missing_field": lambda a: a["statement"].pop("service"),
    "extra_field": lambda a: a["statement"].update({"build_host": "ci-01"}),
    "non_string_field": lambda a: a["statement"].update({"release_tag": 840}),
    "empty_string_field": lambda a: a["statement"].update({"service": ""}),
    "missing_signature": lambda a: a.pop("signature"),
    "statement_not_object": lambda a: a.update({"statement": "v8.4.0"}),
    "bad_instant_form": lambda a: a["statement"].update({"issued_at": "2026-05-12T09:14:00Z"}),
    "bad_digest_prefix": lambda a: a["statement"].update({"artifact_digest": "md5:" + "a" * 64}),
    "bad_digest_length": lambda a: a["statement"].update({"artifact_digest": "sha256:abc"}),
    "bad_digest_uppercase": lambda a: a["statement"].update({"artifact_digest": "sha256:" + "A" * 64}),
}


@pytest.mark.parametrize("label", sorted(SHAPE_VIOLATIONS))
def test_statement_shape_violations_are_unreadable(workspace, label):
    """An attestation that does not match the documented statement shape is unreadable."""
    badges, repo, keyring, out = workspace
    payload = _signed_payload(statement(), SHAPE_VIOLATIONS[label])
    _write_raw_badge(badges, f"{label}.png", payload)
    produced = run_worker(badges, repo, keyring, out)
    entry = produced["badges"][0]
    assert entry["status"] == "badge_unreadable", f"{label} should not be readable"
    assert entry["key_id"] is None
    assert produced == rp.build_snapshot(badges, repo, keyring)


def test_snapshot_bytes_are_canonical_and_compact(workspace):
    """The snapshot file is exactly the canonical compact encoding plus one trailing newline."""
    badges, repo, keyring, out = workspace
    for index, (label, overrides, _extra) in enumerate(RULE_CASES):
        mint_badge(badges, f"{index:02d}-{label}.png", statement(**overrides))
    run_worker(badges, repo, keyring, out)
    raw = out.read_bytes()
    expected = kit.canonical_json(rp.build_snapshot(badges, repo, keyring)) + b"\n"
    assert raw == expected, "snapshot bytes are not the canonical compact encoding"
    assert b", " not in raw and b": " not in raw, "snapshot contains insignificant whitespace"
    assert b"\n" not in raw[:-1], "snapshot must contain no newline other than the trailing one"


def test_reject_statuses_report_the_claimed_branch(workspace):
    """Statuses that never resolve the tag report the branch exactly as the badge claimed it."""
    badges, repo, keyring, out = workspace
    claimed = "release/9.9"
    mint_badge(badges, "untrusted.png", statement(key_id="k-forge", release_branch=claimed))
    mint_badge(badges, "revoked.png",
               statement(key_id="k-build-2025b", issued_at="2026-05-06T00:00:00.000Z",
                         release_branch=claimed))
    mint_badge(badges, "unknown.png", statement(release_tag="v9.9.9", release_branch=claimed))
    mint_badge(badges, "badsig.png", statement(release_branch=claimed),
               tamper={"service": "orders-api"})

    produced = run_worker(badges, repo, keyring, out)
    by_name = {entry["badge"]: entry for entry in produced["badges"]}
    assert by_name["untrusted.png"]["status"] == "key_untrusted"
    assert by_name["revoked.png"]["status"] == "key_revoked"
    assert by_name["unknown.png"]["status"] == "tag_unknown"
    assert by_name["badsig.png"]["status"] == "signature_invalid"
    for entry in by_name.values():
        assert entry["release_branch"] == claimed, "a rejected badge keeps its claimed branch"
        assert entry["exception_id"] is None


def test_resolved_statuses_report_the_changelog_branch(workspace):
    """Statuses that resolve the tag report the branch the changelog attributes to it."""
    badges, repo, keyring, out = workspace
    mint_badge(badges, "conflict.png", statement(release_tag="v8.4.0", release_branch="release/9.0"))
    mint_badge(badges, "accepted.png", statement(release_tag="v8.4.0", release_branch="release/8.4"))
    produced = run_worker(badges, repo, keyring, out)
    by_name = {entry["badge"]: entry for entry in produced["badges"]}
    assert by_name["conflict.png"]["status"] == "branch_conflict"
    assert by_name["conflict.png"]["release_branch"] == "release/8.4"
    assert by_name["accepted.png"]["status"] == "accepted"
    assert by_name["accepted.png"]["release_branch"] == "release/8.4"


# --------------------------------------------------------------------------------------------
# native extractor: correctness and memory safety
# --------------------------------------------------------------------------------------------


def _compile_harness(tmp_path: Path) -> Path:
    binary = tmp_path / "harness"
    result = subprocess.run(
        ["gcc", "-O1", "-g", "-fno-omit-frame-pointer", "-Wall",
         "-I", str(APP / "native"),
         str(Path(__file__).parent / "harness.c"), str(APP / "native" / "attest.c"),
         "-o", str(binary)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"native harness failed to compile: {result.stderr}"
    return binary


def test_native_extractor_recovers_full_multichunk_payload(tmp_path):
    """The native extractor returns the exact concatenated payload of a multi-chunk badge."""
    payload = kit.canonical_json(kit.build_attestation(statement(), SEEDS["k-build-2026a"]))
    badge = tmp_path / "multi.png"
    badge.write_bytes(kit.build_badge_png(payload, segments=4))
    binary = _compile_harness(tmp_path)
    result = subprocess.run([str(binary), str(badge)], capture_output=True)
    assert result.returncode == 0
    assert result.stdout == payload, "extractor truncated or corrupted the multi-chunk payload"


@pytest.mark.parametrize("segments", [1, 2, 4])
def test_native_extractor_is_memory_safe_under_valgrind(tmp_path, segments):
    """Extracting a badge triggers no memory errors under Valgrind for any chunk count."""
    if shutil.which("valgrind") is None:
        pytest.fail("valgrind is required to verify the native extractor")
    payload = kit.canonical_json(kit.build_attestation(statement(), SEEDS["k-build-2026a"]))
    badge = tmp_path / "badge.png"
    badge.write_bytes(kit.build_badge_png(payload, segments=segments))
    binary = _compile_harness(tmp_path)
    result = subprocess.run(
        ["valgrind", "--error-exitcode=1", "--leak-check=full",
         "--errors-for-leak-kinds=definite,indirect", "-q", str(binary), str(badge)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"valgrind reported a memory error:\n{result.stderr}"
    assert result.stdout.encode("utf-8", "surrogatepass") == payload


def test_native_extractor_rejects_a_corrupt_chunk_crc(tmp_path):
    """A badge whose attestation chunk fails its CRC is reported as carrying no payload."""
    payload = kit.canonical_json(kit.build_attestation(statement(), SEEDS["k-build-2026a"]))
    badge = tmp_path / "bad.png"
    badge.write_bytes(kit.build_badge_png(payload, segments=2, corrupt_crc=True))
    binary = _compile_harness(tmp_path)
    result = subprocess.run([str(binary), str(badge)], capture_output=True)
    assert result.returncode == 2, "a corrupt-CRC badge must not yield a payload"
