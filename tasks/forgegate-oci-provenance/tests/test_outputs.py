"""Black-box verification for the ForgeGate OCI provenance admission gate."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


CLI = Path("/app/bin/forgegate")
INDEX_MT = "application/vnd.oci.image.index.v1+json"
MANIFEST_MT = "application/vnd.oci.image.manifest.v1+json"
CONFIG_MT = "application/vnd.oci.image.config.v1+json"
LAYER_MT = "application/vnd.oci.image.layer.v1.tar"


def canonical(value: object) -> bytes:
    """Return contract-canonical JSON bytes without the artifact newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data: bytes) -> str:
    """Return an OCI SHA-256 digest for bytes."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    """Write ordinary input JSON; input whitespace is intentionally not significant."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def add_blob(layout: Path, value: object | bytes, media_type: str) -> dict:
    """Store content-addressed bytes and return their descriptor."""
    raw = value if isinstance(value, bytes) else canonical(value)
    identifier = digest(raw)
    target = layout / "blobs" / "sha256" / identifier.split(":", 1)[1]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"mediaType": media_type, "digest": identifier, "size": len(raw)}


def keypair(directory: Path, key_id: str, role: str) -> tuple[dict, Path]:
    """Generate a fresh Ed25519 identity using the container's OpenSSL."""
    private = directory / f"{key_id}.pem"
    public = directory / f"{key_id}.pub.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", private], check=True)
    subprocess.run(["openssl", "pkey", "-in", private, "-pubout", "-out", public], check=True)
    record = {
        "key_id": key_id,
        "builder_id": "builder://trusted/forge-v4",
        "role": role,
        "public_key_pem": public.read_text(),
        "active_from": "2026-01-01T00:00:00.000Z",
        "active_until": None,
        "revoked_at": None,
    }
    return record, private


def signature(private: Path, payload: dict) -> str:
    """Sign canonical provenance bytes with an Ed25519 private key."""
    message = private.with_suffix(".message")
    message.write_bytes(canonical(payload))
    result = subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", private, "-in", message],
        capture_output=True, check=True,
    )
    message.unlink()
    return base64.b64encode(result.stdout).decode()


def platform_name(platform: dict) -> str:
    """Construct the contract platform identity."""
    return "-".join(str(platform[key]) for key in ("os", "architecture", "variant") if key in platform)


class Case:
    """A fully independent generated admission case."""

    def __init__(self, root: Path, platforms: list[dict] | None = None):
        self.root = root
        self.layout = root / "layout"
        self.out = root / "out"
        self.policy_path = root / "policy.json"
        self.keyring_path = root / "keyring.json"
        self.waivers_path = root / "waivers.json"
        self.platforms = platforms or [{"os": "linux", "architecture": "amd64"}]
        self.private: dict[str, Path] = {}
        keys = []
        for key_id, role in (("build-a", "builder"), ("security-a", "security"), ("build-b", "builder")):
            record, private = keypair(root, key_id, role)
            keys.append(record)
            self.private[key_id] = private
        self.keyring = {"keys": keys}
        self.policy = {
            "allowed_builders": [{
                "builder_id": "builder://trusted/forge-v4",
                "source_prefix": "https://git.example/release/",
                "ref_glob": "refs/tags/v*",
            }],
            "evaluation_time": "2026-06-15T12:00:00.000Z",
            "image": "registry.example/payments/api",
            "platforms": copy.deepcopy(self.platforms),
            "role_minimums": {"builder": 1, "security": 1},
            "signature_threshold": 2,
            "trusted_material_prefixes": ["https://git.example/", "pkg:gem/"],
        }
        self.waivers = {"waivers": []}
        self.payloads: dict[str, dict] = {}
        self.envelopes: dict[str, dict] = {}
        self.manifests: dict[str, dict] = {}
        self.descriptors: dict[str, dict] = {}
        self._build_layout()
        self.save()

    def _build_layout(self) -> None:
        self.layout.mkdir(parents=True)
        write_json(self.layout / "oci-layout", {"imageLayoutVersion": "1.0.0"})
        descriptors = []
        for index, platform in enumerate(self.platforms):
            config = {"architecture": platform["architecture"], "os": platform["os"], "rootfs": {"type": "layers", "diff_ids": []}}
            if "variant" in platform:
                config["variant"] = platform["variant"]
            config_desc = add_blob(self.layout, config, CONFIG_MT)
            layer_desc = add_blob(self.layout, f"layer-{index}-{os.urandom(12).hex()}".encode(), LAYER_MT)
            manifest = {"schemaVersion": 2, "mediaType": MANIFEST_MT, "config": config_desc, "layers": [layer_desc]}
            manifest_desc = add_blob(self.layout, manifest, MANIFEST_MT)
            manifest_desc["platform"] = copy.deepcopy(platform)
            name = platform_name(platform)
            self.manifests[name] = manifest
            self.descriptors[name] = manifest_desc
            descriptors.append(manifest_desc)

            payload = {
                "builder_id": "builder://trusted/forge-v4",
                "build_finished": "2026-06-14T10:05:00.000Z",
                "build_started": "2026-06-14T10:00:00.000Z",
                "commit": hashlib.sha1(f"commit-{index}-{self.root}".encode()).hexdigest(),
                "materials": [
                    {"digest": "sha256:" + "2" * 64, "uri": "https://git.example/release/payments"},
                    {"digest": "sha256:" + "3" * 64, "uri": "pkg:gem/rack@3.1.0"},
                ],
                "ref": "refs/tags/v4.8.0",
                "source_uri": "https://git.example/release/payments",
                "subject_digest": manifest_desc["digest"],
                "vulnerabilities": [],
            }
            envelope = {"payload": payload, "signatures": []}
            self.payloads[name] = payload
            self.envelopes[name] = envelope
            self.resign(name)
        index_doc = {"schemaVersion": 2, "mediaType": INDEX_MT, "manifests": descriptors}
        (self.layout / "index.json").write_bytes(canonical(index_doc))

    def resign(self, name: str, key_ids: tuple[str, ...] = ("build-a", "security-a")) -> None:
        """Replace a platform's signatures and persist its envelope."""
        payload = self.payloads[name]
        self.envelopes[name]["signatures"] = [
            {"key_id": key_id, "signature": signature(self.private[key_id], payload)} for key_id in key_ids
        ]
        hex_digest = self.descriptors[name]["digest"].split(":", 1)[1]
        write_json(self.layout / "evidence" / f"{hex_digest}.provenance.json", self.envelopes[name])

    def add_waiver(self, name: str, finding: dict) -> dict:
        """Append a waiver matching one finding in the named platform."""
        payload = self.payloads[name]
        waiver = {
            "id": "WV-" + hashlib.sha256((name + finding["advisory"]).encode()).hexdigest()[:8],
            "image": self.policy["image"], "platform": name,
            "advisory": finding["advisory"], "package": finding["package"],
            "builder_id": payload["builder_id"], "source_prefix": payload["source_uri"],
            "commit": payload["commit"], "starts_at": "2026-06-01T00:00:00.000Z",
            "expires_at": "2026-07-01T00:00:00.000Z",
        }
        self.waivers["waivers"].append(waiver)
        return waiver

    def save(self) -> None:
        """Persist mutable policy evidence files."""
        write_json(self.policy_path, self.policy)
        write_json(self.keyring_path, self.keyring)
        write_json(self.waivers_path, self.waivers)

    def run(self) -> dict:
        """Run the public command and return its aggregate report."""
        self.save()
        result = subprocess.run([
            CLI, "evaluate", "--layout", self.layout, "--policy", self.policy_path,
            "--keyring", self.keyring_path, "--waivers", self.waivers_path, "--out", self.out,
        ], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads((self.out / "report.json").read_text())


@pytest.fixture
def case(tmp_path: Path) -> Case:
    """Provide a fresh signed OCI layout for each test."""
    return Case(tmp_path)


def assert_canonical_artifacts(case: Case, report: dict) -> None:
    """Check canonical bytes, evidence digest, and per-platform identity."""
    raw = (case.out / "report.json").read_bytes()
    assert raw == canonical(report) + b"\n"
    assert report["evidence_digest"] == hashlib.sha256(canonical(report["platforms"])).hexdigest()
    for verdict in report["platforms"]:
        artifact = case.out / "admission" / f"{verdict['platform']}.json"
        assert artifact.read_bytes() == canonical(verdict) + b"\n"


def test_valid_multiplatform_layout_is_admitted(tmp_path: Path) -> None:
    """Two fully authenticated requested platforms produce deterministic admission records."""
    generated = Case(tmp_path, [{"os": "linux", "architecture": "arm64", "variant": "v8"},
                                {"os": "linux", "architecture": "amd64"}])
    report = generated.run()
    assert report["status"] == "admitted"
    assert [x["platform"] for x in report["platforms"]] == ["linux-amd64", "linux-arm64-v8"]
    assert all(x["signers"] == ["build-a", "security-a"] for x in report["platforms"])
    assert_canonical_artifacts(generated, report)


@pytest.mark.parametrize("mutation", ["layer_bytes", "descriptor_size", "config_platform"])
def test_layout_graph_corruption_is_a_global_failure(case: Case, mutation: str) -> None:
    """Any broken content commitment or platform binding rejects the complete layout."""
    name = "linux-amd64"
    manifest = case.manifests[name]
    if mutation == "layer_bytes":
        target = case.layout / "blobs" / "sha256" / manifest["layers"][0]["digest"].split(":")[1]
        target.write_bytes(target.read_bytes() + b"tamper")
    elif mutation == "descriptor_size":
        index_doc = json.loads((case.layout / "index.json").read_text())
        index_doc["manifests"][0]["size"] += 1
        (case.layout / "index.json").write_bytes(canonical(index_doc))
    else:
        config_desc = manifest["config"]
        target = case.layout / "blobs" / "sha256" / config_desc["digest"].split(":")[1]
        config = json.loads(target.read_text())
        config["architecture"] = "arm64"
        target.write_bytes(canonical(config))
    report = case.run()
    assert report["reasons"] == ["LAYOUT_INVALID"]
    assert report["platforms"] == [] and report["index_digest"] is None
    assert list(case.out.iterdir()) == [case.out / "report.json"]


def test_subject_binding_and_policy_reasons_accumulate_in_precedence(case: Case) -> None:
    """A signed wrong subject and disallowed source/ref are independently reported in fixed order."""
    name = "linux-amd64"
    payload = case.payloads[name]
    payload["subject_digest"] = "sha256:" + "9" * 64
    payload["source_uri"] = "https://evil.example/release/payments"
    payload["ref"] = "refs/heads/main"
    case.resign(name)
    report = case.run()
    assert report["platforms"][0]["reasons"] == ["SUBJECT_MISMATCH", "SOURCE_NOT_ALLOWED", "REF_NOT_ALLOWED"]


def test_duplicate_signature_cannot_satisfy_distinct_role_quorum(case: Case) -> None:
    """Repeating one valid builder signature does not replace the required security signer."""
    name = "linux-amd64"
    case.resign(name, ("build-a",))
    case.envelopes[name]["signatures"] *= 3
    hex_digest = case.descriptors[name]["digest"].split(":")[1]
    write_json(case.layout / "evidence" / f"{hex_digest}.provenance.json", case.envelopes[name])
    verdict = case.run()["platforms"][0]
    assert verdict["signers"] == ["build-a"]
    assert verdict["reasons"] == ["SIGNATURE_POLICY_UNMET"]


def test_key_revocation_boundary_is_inclusive(case: Case) -> None:
    """A signer revoked exactly at build completion cannot contribute to quorum."""
    security = next(x for x in case.keyring["keys"] if x["key_id"] == "security-a")
    security["revoked_at"] = case.payloads["linux-amd64"]["build_finished"]
    verdict = case.run()["platforms"][0]
    assert verdict["signers"] == ["build-a"]
    assert verdict["reasons"] == ["SIGNATURE_POLICY_UNMET"]


@pytest.mark.parametrize("field,bad_value", [
    ("platform", "linux-arm64"),
    ("commit", "0" * 40),
    ("image", "registry.example/other/image"),
    ("builder_id", "builder://other"),
    ("expires_at", "2026-06-15T12:00:00.000Z"),
])
def test_every_waiver_scope_dimension_is_load_bearing(case: Case, field: str, bad_value: str) -> None:
    """Changing any required waiver dimension leaves a high finding unwaived."""
    name = "linux-amd64"
    finding = {"advisory": "CVE-2026-4242", "package": "openssl", "severity": "high"}
    case.payloads[name]["vulnerabilities"] = [finding]
    waiver = case.add_waiver(name, finding)
    waiver[field] = bad_value
    case.resign(name)
    verdict = case.run()["platforms"][0]
    assert verdict["waivers"] == []
    assert verdict["reasons"] == ["VULNERABILITY_UNWAIVED"]


def test_matching_waiver_is_consumed_but_medium_finding_needs_none(case: Case) -> None:
    """An exact active waiver covers one high finding while medium evidence remains report-only."""
    name = "linux-amd64"
    findings = [
        {"advisory": "CVE-2026-1000", "package": "glibc", "severity": "medium"},
        {"advisory": "CVE-2026-4242", "package": "openssl", "severity": "high"},
    ]
    case.payloads[name]["vulnerabilities"] = findings
    waiver = case.add_waiver(name, findings[1])
    case.resign(name)
    verdict = case.run()["platforms"][0]
    assert verdict["status"] == "admitted" and verdict["reasons"] == []
    assert verdict["waivers"] == [waiver["id"]]
    assert verdict["findings"] == findings


def test_missing_and_malformed_evidence_have_terminal_reasons(case: Case) -> None:
    """Missing and malformed provenance do not leak untrusted descriptive fields."""
    name = "linux-amd64"
    path = case.layout / "evidence" / f"{case.descriptors[name]['digest'].split(':')[1]}.provenance.json"
    path.unlink()
    missing = case.run()["platforms"][0]
    assert missing["reasons"] == ["PROVENANCE_MISSING"] and missing["builder_id"] is None
    path.write_text('{"payload":')
    malformed = case.run()["platforms"][0]
    assert malformed["reasons"] == ["PROVENANCE_MALFORMED"] and malformed["findings"] == []


def test_output_replaces_stale_state_and_repeat_run_is_byte_stable(case: Case) -> None:
    """Evaluation removes stale output and repeats with byte-identical artifacts."""
    case.out.mkdir()
    (case.out / "stale-secret.txt").write_text("old")
    first = case.run()
    first_bytes = (case.out / "report.json").read_bytes()
    assert not (case.out / "stale-secret.txt").exists()
    second = case.run()
    second_bytes = (case.out / "report.json").read_bytes()
    assert first == second and first_bytes == second_bytes
    assert_canonical_artifacts(case, second)
