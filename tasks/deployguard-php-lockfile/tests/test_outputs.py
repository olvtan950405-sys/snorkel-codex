"""Black-box tests for the PHP deploy webhook authorization boundary."""
from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import time

import pytest


def fingerprint(lock: dict) -> str:
    """Return the contract fingerprint for a generated Composer lock object."""
    coords = [f"{p['name']}@{p['version']}" for k in ("packages", "packages-dev") for p in lock[k]]
    return hashlib.sha256("\n".join(sorted(coords)).encode()).hexdigest()


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    """Launch the public command against a fresh randomized trust database."""
    root = tmp_path_factory.mktemp("deployguard")
    db_path = root / "trust.sqlite"
    db = sqlite3.connect(db_path)
    db.executescript(Path("/app/docs/schema.sql").read_text())
    now = int(time.time())
    values = {
        "old": ("old-" + secrets.token_hex(16), now - 900, now + 120),
        "new": ("new-" + secrets.token_hex(16), now - 120, now + 900),
        "disabled": ("off-" + secrets.token_hex(16), now - 900, now + 900),
    }
    db.executemany(
        "INSERT INTO signing_keys VALUES (?,?,?,?,?)",
        [(kid, secret, start, end, kid != "disabled") for kid, (secret, start, end) in values.items()],
    )
    lock = {
        "packages": [{"name": "vendor/zeta", "version": "2.1.0", "dist": {"reference": secrets.token_hex(8)}}],
        "packages-dev": [{"name": "alpha/test", "version": "1.7.3"}],
        "content-hash": secrets.token_hex(16),
    }
    fp = fingerprint(lock)
    db.execute("INSERT INTO deploy_policies VALUES (?,?)", ("production", fp))
    db.commit(); db.close()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    env = os.environ.copy(); env["PHP_CLI_SERVER_WORKERS"] = "4"
    proc = subprocess.Popen(
        ["/app/bin/deployguard", "serve", "--host", "127.0.0.1", "--port", str(port), "--database", str(db_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    for _ in range(100):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=.2); conn.request("GET", "/healthz")
            if conn.getresponse().status == 200: break
        except OSError: time.sleep(.05)
    else:
        proc.terminate(); raise RuntimeError("deployguard did not start")
    yield {"port": port, "db": db_path, "keys": values, "lock": lock, "fp": fp}
    proc.terminate()
    try: proc.wait(timeout=3)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait()


def body_for(s, **changes) -> bytes:
    """Build compact request bytes, permitting focused test mutations."""
    value = {"release_id": "release-" + secrets.token_hex(5), "environment": "production", "lock_fingerprint": s["fp"], "composer_lock": s["lock"]}
    value.update(changes)
    return json.dumps(value, separators=(",", ":")).encode()


def request(s, body: bytes, *, kid="new", timestamp=None, nonce=None, signature=None, extra_headers=None):
    """Send one signed authorization request and decode its exact JSON response."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    nonce = secrets.token_hex(16) if nonce is None else nonce
    message = str(timestamp).encode() + b"\n" + nonce.encode() + b"\n" + body
    if signature is None:
        signature = "sha256=" + hmac.new(s["keys"][kid][0].encode(), message, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Deploy-Key-Id": kid, "X-Deploy-Timestamp": str(timestamp), "X-Deploy-Nonce": nonce, "X-Deploy-Signature": signature}
    headers.update(extra_headers or {})
    conn = http.client.HTTPConnection("127.0.0.1", s["port"], timeout=5)
    conn.request("POST", "/v1/deploy/authorize", body=body, headers=headers)
    response = conn.getresponse(); raw = response.read(); conn.close()
    assert response.getheader("Content-Type", "").split(";", 1)[0] == "application/json"
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    return response.status, json.loads(raw)


def nonce_count(s) -> int:
    """Count durable accepted nonce claims."""
    with sqlite3.connect(s["db"]) as db: return db.execute("SELECT count(*) FROM accepted_nonces").fetchone()[0]


def test_health_and_valid_authorization(service):
    """Health remains available and a freshly signed policy-compliant deploy is accepted."""
    conn = http.client.HTTPConnection("127.0.0.1", service["port"]); conn.request("GET", "/healthz")
    response = conn.getresponse(); assert response.status == 200; assert response.read() == b'{"status":"ok"}\n'
    body = body_for(service); release = json.loads(body)["release_id"]
    assert request(service, body) == (200, {"authorized": True, "lock_fingerprint": service["fp"], "release_id": release})


def test_raw_bytes_are_authenticated(service):
    """Whitespace changes after signing fail because the HMAC covers exact wire bytes."""
    body = body_for(service); ts = int(time.time()); nonce = secrets.token_hex(16)
    mac = hmac.new(service["keys"]["new"][0].encode(), str(ts).encode()+b"\n"+nonce.encode()+b"\n"+body, hashlib.sha256).hexdigest()
    changed = body.replace(b'"environment":', b'"environment" :', 1)
    before = nonce_count(service)
    assert request(service, changed, timestamp=ts, nonce=nonce, signature="sha256="+mac) == (401, {"error": "unauthorized"})
    assert nonce_count(service) == before


def test_key_rollover_and_timestamp_rules(service):
    """Database keys, half-open rollover intervals, disabled keys, and clock skew are enforced."""
    body = body_for(service)
    assert request(service, body, kid="old") [0] == 200
    for kid, ts in [("disabled", int(time.time())), ("old", service["keys"]["old"][2]), ("new", int(time.time())-301)]:
        before = nonce_count(service)
        assert request(service, body_for(service), kid=kid, timestamp=ts) == (401, {"error": "unauthorized"})
        assert nonce_count(service) == before


def test_strict_headers_and_body_schema(service):
    """Malformed signature/header forms and unexpected top-level JSON members are refused."""
    before = nonce_count(service)
    assert request(service, body_for(service), signature="sha256=" + "A"*64) == (400, {"error": "invalid_request"})
    bad = body_for(service, surprise=True)
    assert request(service, bad) == (400, {"error": "invalid_request"})
    assert nonce_count(service) == before


def test_lockfile_canonicalization_and_policy(service):
    """Package order is irrelevant while duplicates, asserted mismatches, and unknown policy are rejected."""
    reordered = dict(service["lock"]); reordered["packages"], reordered["packages-dev"] = reordered["packages-dev"], reordered["packages"]
    assert request(service, body_for(service, composer_lock=reordered))[0] == 200
    duplicate = dict(service["lock"]); duplicate["packages-dev"] = service["lock"]["packages-dev"] + [service["lock"]["packages"][0]]
    for body in [body_for(service, composer_lock=duplicate), body_for(service, lock_fingerprint="0"*64), body_for(service, environment="staging")]:
        before = nonce_count(service)
        assert request(service, body) == (422, {"error": "policy_rejected"})
        assert nonce_count(service) == before


def test_replay_and_concurrent_claim_are_atomic(service):
    """A nonce is accepted once, including when two workers claim it simultaneously."""
    body = body_for(service); nonce = secrets.token_hex(16)
    assert request(service, body, nonce=nonce)[0] == 200
    assert request(service, body, nonce=nonce) == (409, {"error": "replayed"})
    race_body = body_for(service); race_nonce = secrets.token_hex(16)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(service, race_body, nonce=race_nonce)[0], range(2)))
    assert sorted(results) == [200, 409]
    with sqlite3.connect(service["db"]) as db:
        assert db.execute("SELECT count(*) FROM accepted_nonces WHERE key_id='new' AND nonce=?", (race_nonce,)).fetchone()[0] == 1
