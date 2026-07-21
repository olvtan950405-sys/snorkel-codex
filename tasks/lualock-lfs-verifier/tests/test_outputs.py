"""Black-box verification for the Lua model-lock gate."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pytest


def run(*args: str, cwd: Path | None = None, input_bytes: bytes | None = None) -> bytes:
    """Run one required local tool without a shell and return stdout."""
    return subprocess.run(args, cwd=cwd, input=input_bytes, check=True, stdout=subprocess.PIPE).stdout


def free_port() -> int:
    """Reserve an ephemeral loopback port for a short-lived server."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Gate:
    """A lockguard process configured for one immutable test fixture."""

    def __init__(self, lock: Path, key: Path, remote: Path):
        self.port = free_port()
        env = os.environ.copy()
        env.update(MODEL_LOCK_PATH=str(lock), MAINTAINER_KEY_PATH=str(key), MODEL_REMOTE=str(remote))
        self.proc = subprocess.Popen(
            ["/app/bin/lockguard", "--port", str(self.port)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for _ in range(100):
            try:
                if self.request("GET", "/healthz")[0] == 200:
                    break
            except OSError:
                time.sleep(0.03)
        else:
            stdout, stderr = self.proc.communicate(timeout=2)
            raise AssertionError(f"lockguard failed to start: {stdout!r} {stderr!r}")

    def request(self, method: str, path: str) -> tuple[int, bytes, str]:
        """Issue an HTTP request and preserve exact body and media type."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        connection.request(method, path, body=b"" if method == "POST" else None)
        response = connection.getresponse()
        result = response.status, response.read(), response.getheader("Content-Type", "")
        connection.close()
        return result

    def close(self) -> None:
        """Terminate and reap the worker."""
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=2)


class Fixture:
    """Fresh maintainer keys, LFS model remote, and signed-lock factory."""

    def __init__(self, root: Path, remote_name: str = "model.git"):
        self.root = root
        self.repo = root / "work"
        self.remote = root / remote_name
        self.private = root / "private.pem"
        self.public = root / "public.pem"
        run("openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(self.private))
        run("openssl", "pkey", "-in", str(self.private), "-pubout", "-out", str(self.public))
        run("git", "init", "-q", str(self.repo))
        run("git", "config", "user.name", "Fixture", cwd=self.repo)
        run("git", "config", "user.email", "fixture@example.invalid", cwd=self.repo)
        run("git", "lfs", "install", "--local", cwd=self.repo)
        (self.repo / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")
        (self.repo / "models").mkdir()
        self.content = b"fresh model bytes\x00\xff\n"
        (self.repo / "models" / "weights.bin").write_bytes(self.content)
        run("git", "add", ".", cwd=self.repo)
        run("git", "commit", "-qm", "fresh model", cwd=self.repo)
        self.commit = run("git", "rev-parse", "HEAD", cwd=self.repo).decode().strip()
        run("git", "clone", "-q", "--bare", str(self.repo), str(self.remote))
        run("git", "remote", "add", "origin", str(self.remote), cwd=self.repo)
        run("git", "lfs", "push", "--all", "origin", cwd=self.repo)
        self.digest = hashlib.sha256(self.content).hexdigest()

    def lock(self, name: str = "lock", *, revision: str | None = None,
             digest: str | None = None, size: int | None = None,
             artifact: str = "models/weights.bin", model: str = "org/fresh-model") -> Path:
        """Write a correctly signed lock with selected semantic values."""
        prefix = (
            "lock-version 1\n"
            f"model {model}\n"
            f"revision {revision or self.commit}\n"
            f"artifact {artifact} {digest or self.digest} {len(self.content) if size is None else size}\n"
        ).encode()
        signature = run("openssl", "dgst", "-sha256", "-sign", str(self.private), input_bytes=prefix)
        path = self.root / name
        path.write_bytes(prefix + b"signature " + base64.b64encode(signature) + b"\n")
        return path


def verdict(lock: Path, key: Path, remote: Path) -> tuple[int, dict, bytes, str]:
    """Start the public command and request one verification verdict."""
    gate = Gate(lock, key, remote)
    try:
        status, body, media = gate.request("POST", "/verify-lock")
        return status, json.loads(body), body, media
    finally:
        gate.close()


@pytest.fixture()
def fixture(tmp_path: Path) -> Fixture:
    """Create isolated inputs for each behavioral assertion."""
    return Fixture(tmp_path)


def test_healthz_is_canonical_json(fixture: Fixture) -> None:
    """The public health endpoint remains available and byte-canonical."""
    gate = Gate(fixture.lock(), fixture.public, fixture.remote)
    try:
        status, body, media = gate.request("GET", "/healthz")
        assert (status, body, media) == (200, b'{"status":"ok"}\n', "application/json")
    finally:
        gate.close()


def test_fresh_signed_lfs_lock_is_accepted(fixture: Fixture) -> None:
    """A fresh key, remote, commit, and LFS artifact verify without fixture constants."""
    status, data, body, media = verdict(fixture.lock(), fixture.public, fixture.remote)
    assert status == 200 and media == "application/json"
    assert data == {"artifacts": 1, "commit": fixture.commit, "status": "accepted"}
    assert body == json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"


@pytest.mark.parametrize("marker", ["<<<<<<< HEAD", "=======", ">>>>>>> branch"])
def test_conflict_markers_are_rejected_before_parsing(fixture: Fixture, marker: str) -> None:
    """Each unresolved merge-marker form produces LOCK_CONFLICT."""
    path = fixture.root / "conflicted.lock"
    path.write_text(f"lock-version 1\n{marker}\n")
    assert verdict(path, fixture.public, fixture.remote)[1] == {"reasons": ["LOCK_CONFLICT"], "status": "rejected"}


@pytest.mark.parametrize("mutation", ["blank", "duplicate", "traversal", "unsorted", "crlf", "bad-size"])
def test_strict_lock_grammar_rejects_ambiguous_inputs(fixture: Fixture, mutation: str) -> None:
    """Blank/unknown ordering, unsafe paths, line endings, and numbers are invalid."""
    path = fixture.lock("mutated.lock")
    raw = path.read_bytes()
    if mutation == "blank": raw = raw.replace(b"model ", b"\nmodel ", 1)
    elif mutation == "duplicate": raw = raw.replace(b"revision ", b"model org/again\nrevision ", 1)
    elif mutation == "traversal": raw = raw.replace(b"models/weights.bin", b"../weights.bin")
    elif mutation == "unsorted": raw = raw.replace(b"artifact ", b"artifact z.bin " + fixture.digest.encode() + b" 1\nartifact ", 1)
    elif mutation == "crlf": raw = raw.replace(b"\n", b"\r\n")
    else: raw = raw.replace(str(len(fixture.content)).encode() + b"\n", b"00\n", 1)
    path.write_bytes(raw)
    assert verdict(path, fixture.public, fixture.remote)[1] == {"reasons": ["INVALID_LOCK"], "status": "rejected"}


def test_signature_authenticates_every_locked_field(fixture: Fixture) -> None:
    """Changing an artifact digest after signing invalidates the lock signature."""
    path = fixture.lock()
    raw = path.read_bytes().replace(fixture.digest.encode(), ("0" * 64).encode(), 1)
    path.write_bytes(raw)
    assert verdict(path, fixture.public, fixture.remote)[1] == {"reasons": ["LOCK_SIGNATURE_INVALID"], "status": "rejected"}


def test_commit_must_be_reachable_from_remote_ref(fixture: Fixture) -> None:
    """A signed but nonexistent object id is a remote-reference mismatch."""
    path = fixture.lock(revision="0" * 40)
    assert verdict(path, fixture.public, fixture.remote)[1] == {"reasons": ["REMOTE_REF_MISMATCH"], "status": "rejected"}


def test_pointer_metadata_must_match_lock(fixture: Fixture) -> None:
    """A signed digest inconsistent with the committed pointer is explicitly rejected."""
    path = fixture.lock(digest="1" * 64)
    reasons = verdict(path, fixture.public, fixture.remote)[1]["reasons"]
    assert "LFS_POINTER_INVALID" in reasons and "ARTIFACT_DIGEST_MISMATCH" in reasons


def test_missing_artifact_is_not_treated_as_ordinary_git_content(fixture: Fixture) -> None:
    """A signed path absent from the commit fails LFS pointer validation."""
    path = fixture.lock(artifact="models/missing.bin")
    reasons = verdict(path, fixture.public, fixture.remote)[1]["reasons"]
    assert "LFS_POINTER_INVALID" in reasons


def test_remote_operand_with_shell_metacharacters_is_safe_and_supported(tmp_path: Path) -> None:
    """A configured remote path containing shell syntax remains one inert operand."""
    fixture = Fixture(tmp_path, "remote;touch PWNED.git")
    status, data, _, _ = verdict(fixture.lock(), fixture.public, fixture.remote)
    assert status == 200 and data["status"] == "accepted"
    assert not (tmp_path / "PWNED.git").exists()
    assert not Path("/app/PWNED.git").exists()


def test_required_posix_tools_are_used_by_active_lua_source() -> None:
    """The repaired implementation actively drives every required verification tool."""
    source = Path("/app/verify_service.lua").read_text()
    for token in ('"git"', '"lfs"', '"openssl"', '"sha256sum"'):
        assert token in source
    assert "os.execute" in source


def test_default_conflicted_fixture_is_repaired_and_inputs_remain_unchanged() -> None:
    """The shipped lock verifies and an endpoint call does not mutate trusted inputs."""
    lock = Path("/app/deps.lock")
    remote = Path("/srv/model-remotes/sentence-transformers/all-MiniLM-L6-v2.git")
    before_lock = hashlib.sha256(lock.read_bytes()).digest()
    before_head = run("git", "--git-dir=" + str(remote), "rev-parse", "HEAD")
    status, data, _, _ = verdict(lock, Path("/app/config/maintainer-public.pem"), remote)
    assert status == 200 and data["status"] == "accepted"
    assert hashlib.sha256(lock.read_bytes()).digest() == before_lock
    assert run("git", "--git-dir=" + str(remote), "rev-parse", "HEAD") == before_head
