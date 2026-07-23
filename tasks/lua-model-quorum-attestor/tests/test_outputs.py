#!/usr/bin/env python3
"""Black-box checks for the quorum-signed multi-model release attestor."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest


def run(*args: str, cwd: Path | None = None, data: bytes | None = None) -> bytes:
    """Run a local tool without a shell and capture stdout."""
    return subprocess.run(args, cwd=cwd, input=data, check=True, stdout=subprocess.PIPE).stdout


def port() -> int:
    """Allocate a short-lived loopback port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Server:
    """One attestor process with immutable startup configuration."""

    def __init__(self, lock: Path, keys: Path, mirrors: Path):
        self.port = port()
        env = os.environ.copy()
        env.update(RELEASE_LOCK_PATH=str(lock), MAINTAINER_KEY_DIR=str(keys), MODEL_MIRROR_ROOT=str(mirrors))
        self.process = subprocess.Popen(
            ["/app/bin/model-attestor", "--port", str(self.port)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for _ in range(100):
            try:
                if self.request("GET", "/healthz")[0] == 200:
                    break
            except OSError:
                time.sleep(0.03)
        else:
            out, err = self.process.communicate(timeout=2)
            raise AssertionError(f"attestor did not start: {out!r} {err!r}")

    def request(self, method: str, path: str) -> tuple[int, bytes, str]:
        """Make one request and preserve exact response bytes."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=25)
        connection.request(method, path, body=b"" if method == "POST" else None)
        response = connection.getresponse()
        result = response.status, response.read(), response.getheader("Content-Type", "")
        connection.close()
        return result

    def close(self) -> None:
        """Terminate and reap the process."""
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)


class Release:
    """Fresh keyring, annotated LFS mirrors, and signed-lock factory."""

    def __init__(self, root: Path, mirror_name: str = "mirrors"):
        self.root = root
        self.mirrors = root / mirror_name
        self.keys = root / "keys"
        self.private = root / "private"
        self.keys.mkdir(parents=True)
        self.private.mkdir()
        self.mirrors.mkdir()
        for key in ("alpha", "beta", "gamma"):
            run(
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(self.private / f"{key}.pem"),
            )
            run(
                "openssl",
                "pkey",
                "-in",
                str(self.private / f"{key}.pem"),
                "-pubout",
                "-out",
                str(self.keys / f"{key}.pem"),
            )
        self.models = [
            self._model("encoder", "org/encoder", "weights.bin", b"encoder fresh bytes\n"),
            self._model("reranker", "org/reranker", "model.bin", b"reranker fresh bytes\x00\n"),
        ]
        self.models.sort(key=lambda item: item["model"])

    def _model(self, mirror: str, model: str, artifact: str, content: bytes) -> dict[str, object]:
        repo = self.root / f"work-{mirror}"
        remote = self.mirrors / f"{mirror}.git"
        run("git", "init", "-q", str(repo))
        run("git", "config", "user.name", "Fixture", cwd=repo)
        run("git", "config", "user.email", "fixture@example.invalid", cwd=repo)
        run("git", "lfs", "install", "--local", cwd=repo)
        (repo / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")
        (repo / artifact).write_bytes(content)
        run("git", "add", ".", cwd=repo)
        run("git", "commit", "-qm", "model snapshot", cwd=repo)
        run("git", "tag", "-a", "approved-v2", "-m", "approved", cwd=repo)
        commit = run("git", "rev-parse", "HEAD", cwd=repo).decode().strip()
        run("git", "clone", "-q", "--bare", str(repo), str(remote))
        run("git", "remote", "add", "origin", str(remote), cwd=repo)
        run("git", "lfs", "push", "--all", "origin", cwd=repo)
        return {"mirror": mirror, "model": model, "artifact": artifact, "content": content,
                "digest": hashlib.sha256(content).hexdigest(), "size": len(content), "commit": commit,
                "remote": remote, "repo": repo}

    def lock(self, name: str = "release.lock", *, quorum: int = 2,
             signers: tuple[str, ...] = ("alpha", "beta"), digest_override: str | None = None) -> Path:
        """Create a canonical manifest and sign its shared exact prefix."""
        lines = ["release-lock 1", "release fresh-pack-v2", f"quorum {quorum}"]
        for index, model in enumerate(self.models):
            digest = digest_override if index == 0 and digest_override else model["digest"]
            lines.append(
                f"model {model['model']} {model['mirror']} approved-v2 "
                f"{model['commit']} {model['artifact']} {digest} {model['size']}"
            )
        prefix = ("\n".join(lines) + "\n").encode()
        raw = bytearray(prefix)
        for signer in signers:
            signature = run("openssl", "dgst", "-sha256", "-sign", str(self.private / f"{signer}.pem"), data=prefix)
            raw.extend(f"signer {signer} ".encode() + base64.b64encode(signature) + b"\n")
        path = self.root / name
        path.write_bytes(raw)
        return path


def attest(lock: Path, keys: Path, mirrors: Path) -> tuple[int, dict, bytes, str]:
    """Run the public endpoint once and decode its verdict."""
    server = Server(lock, keys, mirrors)
    try:
        status, body, media = server.request("POST", "/attest-release")
        return status, json.loads(body), body, media
    finally:
        server.close()


@pytest.fixture()
def release(tmp_path: Path) -> Release:
    """Provide independent generated cryptographic and Git inputs."""
    return Release(tmp_path)


def test_health_endpoint_is_exact(release: Release) -> None:
    """The unsigned health endpoint returns canonical JSON."""
    server = Server(release.lock(), release.keys, release.mirrors)
    try:
        assert server.request("GET", "/healthz") == (200, b'{"status":"ok"}\n', "application/json")
    finally:
        server.close()


def test_fresh_quorum_release_produces_independent_evidence_receipt(release: Release) -> None:
    """Fresh keys and two generated mirrors produce the exact aggregate receipt."""
    evidence = b"".join(
        f"{m['model']} {m['commit']} {m['artifact']} {m['digest']} {m['size']}\n".encode()
        for m in release.models
    )
    expected = {"evidence_sha256": hashlib.sha256(evidence).hexdigest(), "models": 2,
                "release": "fresh-pack-v2", "signers": ["alpha", "beta"], "status": "accepted"}
    status, data, body, media = attest(release.lock(), release.keys, release.mirrors)
    assert status == 200 and media == "application/json" and data == expected
    assert body == json.dumps(expected, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_quorum_counts_only_distinct_valid_signatures(release: Release) -> None:
    """One authentic signature cannot satisfy a two-maintainer threshold."""
    result = attest(release.lock(signers=("alpha",)), release.keys, release.mirrors)[1]
    assert result == {"reasons": ["QUORUM_NOT_MET"], "status": "rejected"}


def test_success_receipt_excludes_an_invalid_extra_signer(release: Release) -> None:
    """An invalid third signature neither defeats quorum nor appears in signers."""
    path = release.lock(signers=("alpha", "beta", "gamma"))
    lines = path.read_bytes().splitlines(keepends=True)
    prefix, signature = lines[-1].split(b" ", 2)[1:]
    replacement = b"A" if signature[:1] != b"A" else b"B"
    lines[-1] = b"signer " + prefix + b" " + replacement + signature[1:]
    path.write_bytes(b"".join(lines))

    status, data, _, _ = attest(path, release.keys, release.mirrors)
    assert status == 200
    assert data["signers"] == ["alpha", "beta"]


def test_signature_binds_every_model_record(release: Release) -> None:
    """Editing a signed commit without resigning loses quorum."""
    path = release.lock()
    raw = path.read_bytes()
    raw = raw.replace(str(release.models[0]["commit"]).encode(), b"0" * 40, 1)
    path.write_bytes(raw)
    assert attest(path, release.keys, release.mirrors)[1]["reasons"] == ["QUORUM_NOT_MET", "TAG_BINDING_INVALID"]


def test_lightweight_tag_does_not_satisfy_annotated_tag_binding(release: Release) -> None:
    """A tag name pointing directly at a commit is rejected even when the commit matches."""
    model = release.models[0]
    remote = Path(model["remote"])
    run("git", "--git-dir=" + str(remote), "tag", "-d", "approved-v2")
    run("git", "--git-dir=" + str(remote), "tag", "approved-v2", str(model["commit"]))
    reasons = attest(release.lock(), release.keys, release.mirrors)[1]["reasons"]
    assert reasons == ["TAG_BINDING_INVALID"]


def test_annotated_tag_must_peel_to_the_locked_commit(release: Release) -> None:
    """A genuine annotated tag over a different commit does not bind the lock."""
    model = release.models[0]
    repo = Path(model["repo"])
    remote = Path(model["remote"])
    run("git", "commit", "--allow-empty", "-qm", "different snapshot", cwd=repo)
    run("git", "tag", "-f", "-a", "approved-v2", "-m", "moved approval", cwd=repo)
    run("git", "push", "-f", "origin", "refs/tags/approved-v2", cwd=repo)
    assert run("git", "--git-dir=" + str(remote), "cat-file", "-t", "refs/tags/approved-v2") == b"tag\n"

    reasons = attest(release.lock(), release.keys, release.mirrors)[1]["reasons"]
    assert reasons == ["TAG_BINDING_INVALID"]


def test_lfs_pointer_and_materialized_digest_are_both_enforced(release: Release) -> None:
    """A signed digest different from the committed pointer cannot be certified."""
    reasons = attest(release.lock(digest_override="1" * 64), release.keys, release.mirrors)[1]["reasons"]
    assert "LFS_POINTER_INVALID" in reasons


@pytest.mark.parametrize("marker", ["<<<<<<< HEAD", "=======", ">>>>>>> branch"])
def test_each_rebase_marker_is_reported_as_conflict(release: Release, marker: str) -> None:
    """Unresolved rebase syntax is distinguished from ordinary malformed input."""
    path = release.root / "conflict.lock"
    path.write_text(f"release-lock 1\n{marker}\n")
    assert attest(path, release.keys, release.mirrors)[1] == {"reasons": ["LOCK_CONFLICT"], "status": "rejected"}


@pytest.mark.parametrize("mutation", ["traversal", "duplicate", "unsorted", "crlf", "zero-quorum"])
def test_manifest_grammar_rejects_unsafe_or_ambiguous_forms(release: Release, mutation: str) -> None:
    """Paths, uniqueness, ordering, line endings, and quorum grammar are strict."""
    path = release.lock()
    raw = path.read_bytes()
    if mutation == "traversal":
        raw = raw.replace(b"weights.bin", b"../weights.bin", 1)
    elif mutation == "duplicate":
        raw = raw.replace(b"signer beta ", b"signer alpha ", 1)
    elif mutation == "unsorted":
        raw = raw.replace(b"model org/encoder ", b"model zzz/encoder ", 1)
    elif mutation == "crlf":
        raw = raw.replace(b"\n", b"\r\n")
    else:
        raw = raw.replace(b"quorum 2", b"quorum 0", 1)
    path.write_bytes(raw)
    assert attest(path, release.keys, release.mirrors)[1] == {"reasons": ["INVALID_LOCK"], "status": "rejected"}


def test_shell_metacharacters_in_configured_mirror_root_are_inert(tmp_path: Path) -> None:
    """A mirror-root path containing shell syntax remains a single safe operand."""
    release = Release(tmp_path, "mirrors;touch PWNED")
    status, data, _, _ = attest(release.lock(), release.keys, release.mirrors)
    assert status == 200 and data["status"] == "accepted"
    assert not (tmp_path / "PWNED").exists() and not Path("/app/PWNED").exists()


def test_shipped_release_is_repaired_without_mutating_trust_inputs() -> None:
    """The oracle repairs the default conflict and endpoint verification stays read-only."""
    lock = Path("/app/release.lock")
    before = hashlib.sha256(lock.read_bytes()).digest()
    status, data, _, _ = attest(lock, Path("/app/config/maintainers"), Path("/srv/model-mirrors"))
    assert status == 200 and data["models"] == 2 and data["signers"] == ["alice", "bob"]
    assert hashlib.sha256(lock.read_bytes()).digest() == before
