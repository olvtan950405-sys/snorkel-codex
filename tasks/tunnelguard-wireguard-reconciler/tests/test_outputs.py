"""Black-box verification for tunnelguard policy reconciliation."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

BIN = Path("/app/bin/tunnelguard")


def canonical(value):
    """Return the contract's canonical JSON bytes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class EventHandler(BaseHTTPRequestHandler):
    """Serve test-owned event evidence and record queries."""

    events = {}
    queries = []

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        peer = parse_qs(parsed.query).get("peer_id", [""])[0]
        type(self).queries.append(peer)
        body = canonical(type(self).events.get(peer, []))
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        """Suppress fixture server logging."""


@contextmanager
def event_server(events):
    """Run a local event service on an ephemeral port."""
    EventHandler.events = events
    EventHandler.queries = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), EventHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", EventHandler.queries
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def workspace(tmp_path):
    """Copy the shipped inputs into an isolated mutable workspace."""
    db = tmp_path / "gateway.db"
    shutil.copy2("/app/data/gateway.db", db)
    policy = tmp_path / "policy.yaml"
    shutil.copy2("/app/data/access-policy.yaml", policy)
    events = json.loads(Path("/app/data/events.json").read_text())
    return db, policy, events, tmp_path / "out"


def run_case(workspace, mutate=None):
    """Run tunnelguard once and return parsed and raw artifacts."""
    db, policy, events, out = workspace
    if mutate:
        mutate(sqlite3.connect(db), policy, events)
    with event_server(events) as (base, queries):
        env = os.environ | {
            "TUNNELGUARD_DB": str(db),
            "TUNNELGUARD_POLICY": str(policy),
            "TUNNELGUARD_OUT": str(out),
            "KEY_EVENT_API_BASE": base,
        }
        subprocess.run([BIN], env=env, check=True, timeout=15)
    raw = (out / "audit/peer-access.json").read_bytes()
    return json.loads(raw), raw, out, list(queries)


def by_id(report):
    """Index report peers by ID."""
    return {peer["peer_id"]: peer for peer in report["peers"]}


def test_shipped_policy_covers_temporal_and_key_verdicts(workspace):
    """Verify active, staged rotation, expired access, and exact-time compromise verdicts."""
    report, _, _, _ = run_case(workspace)
    peers = by_id(report)
    assert peers["alice"]["status"] == "active"
    assert peers["bob"]["status"] == "rotate_key"
    assert peers["carol"]["status"] == "access_expired"
    assert peers["dave"]["status"] == "key_revoked"


def test_disabled_peers_are_omitted_and_not_queried(workspace):
    """Verify disabled peers produce no audit row or key-event request."""
    report, _, _, queries = run_case(workspace)
    assert "disabled" not in by_id(report)
    assert sorted(queries) == ["alice", "bob", "carol", "dave"]


def test_report_is_canonical_and_digest_binds_peer_array(workspace):
    """Verify canonical bytes, full status counts, and the independent peers digest."""
    report, raw, _, _ = run_case(workspace)
    assert raw == canonical(report) + b"\n"
    assert set(report["counts"]) == {"access_expired", "active", "address_conflict", "key_revoked", "policy_denied", "quarantined", "rotate_key", "route_conflict"}
    assert report["sha256"] == hashlib.sha256(canonical(report["peers"])).hexdigest()


def test_enforcement_contains_only_active_peers(workspace):
    """Verify rejected peers never enter WireGuard or nftables enforcement."""
    _, _, out, _ = run_case(workspace)
    wg = (out / "wireguard/wg0.conf").read_text()
    nft = (out / "firewall/tunnelguard.nft").read_text()
    assert "# peer_id = alice" in wg
    assert all(f"# peer_id = {peer}" not in wg for peer in ("bob", "carol", "dave"))
    assert "peer_alice_git" in nft and "peer_alice_metrics" in nft


def test_group_deny_wins_independent_of_membership_order(workspace):
    """Verify a deny from any group removes a service allowed by another group."""
    def mutate(_con, policy, _events):
        text = policy.read_text().replace(
            'allow: ["git", "metrics"]',
            'allow: ["git", "metrics", "prod-db"]',
        )
        policy.write_text(text)
    report, _, _, _ = run_case(workspace, mutate)
    assert "prod-db" not in by_id(report)["alice"]["allowed_services"]


def test_emergency_start_inclusive_and_expiry_exclusive(workspace):
    """Verify emergency access is valid at start and invalid exactly at expiry."""
    def mutate(con, _policy, _events):
        con.execute("update emergency_access set starts_at='2026-07-01T12:00:00Z', expires_at='2026-07-01T13:00:00Z' where peer_id='carol'")
        con.commit()
    report, _, _, _ = run_case(workspace, mutate)
    carol = by_id(report)["carol"]
    assert carol["allowed_services"] == ["prod-db"]
    assert carol["status"] == "address_conflict"


def test_invalid_address_allocates_lowest_usable_unreserved(workspace):
    """Verify deterministic numeric allocation skips gateway and assigned addresses."""
    def mutate(con, _policy, _events):
        con.execute("update peers set address='192.0.2.9' where peer_id='alice'")
        con.commit()
    report, _, _, _ = run_case(workspace, mutate)
    assert by_id(report)["alice"]["assigned_address"] == "10.70.0.4"


def test_mapped_ipv4_normalizes_before_duplicate_detection(workspace):
    """Verify IPv4-mapped IPv6 and plain IPv4 denote the same assigned address."""
    def mutate(con, _policy, _events):
        con.execute("update peers set address='::ffff:10.70.0.2' where peer_id='carol'")
        con.execute("delete from emergency_access where peer_id='carol'")
        con.execute("insert into memberships values ('carol','engineers')")
        con.commit()
    report, _, _, _ = run_case(workspace, mutate)
    assert by_id(report)["carol"]["assigned_address"] == "10.70.0.2"
    assert by_id(report)["carol"]["status"] == "address_conflict"


def test_route_overlap_is_numeric_and_first_peer_wins(workspace):
    """Verify numeric route overlap rejects only the later peer by ID."""
    def mutate(con, _policy, _events):
        con.execute("update peers set public_key='key-bob-new', previous_key=null where peer_id='bob'")
        con.execute("update routes set cidr='10.80.10.64/26' where peer_id='bob'")
        con.commit()
    report, _, _, _ = run_case(workspace, mutate)
    assert by_id(report)["alice"]["status"] == "active"
    assert by_id(report)["bob"]["status"] == "route_conflict"


def test_route_must_be_contained_by_effective_service(workspace):
    """Verify a route outside every allowed service quarantines its peer."""
    def mutate(con, _policy, _events):
        con.execute("update routes set cidr='10.99.0.0/24' where peer_id='alice'")
        con.commit()
    report, _, _, _ = run_case(workspace, mutate)
    assert by_id(report)["alice"]["status"] == "quarantined"


def test_future_compromise_has_no_effect(workspace):
    """Verify key events strictly after evaluation do not revoke authority."""
    def mutate(_con, _policy, events):
        events["alice"] = [{"kind":"compromised","key":"key-alice","at":"2026-07-01T12:00:01Z"}]
    report, _, _, _ = run_case(workspace, mutate)
    assert by_id(report)["alice"]["status"] == "active"


def test_inconsistent_rotation_history_quarantines(workspace):
    """Verify an unstaged latest rotation target is inconsistent evidence."""
    def mutate(_con, _policy, events):
        events["alice"] = [
            {
                "kind": "rotated",
                "old_key": "key-alice",
                "new_key": "key-other",
                "at": "2026-06-01T00:00:00Z",
            }
        ]

    report, _, _, _ = run_case(workspace, mutate)
    assert by_id(report)["alice"]["status"] == "quarantined"


def test_input_row_order_and_cidr_formatting_are_invariant(workspace):
    """Verify equivalent network spelling and reordered evidence leave output identical."""
    first, raw1, _, _ = run_case(workspace)
    db, policy, events, out = workspace
    shutil.rmtree(out)
    con = sqlite3.connect(db)
    con.execute("update routes set cidr='10.80.10.7/25' where peer_id='alice'")
    con.commit()
    con.close()
    events["bob"] = list(reversed(events["bob"]))
    second, raw2, _, _ = run_case(workspace)
    assert first == second and raw1 == raw2


def test_repeated_runs_are_byte_identical(workspace):
    """Verify all four artifacts are deterministic across repeated runs."""
    _, _, out, _ = run_case(workspace)
    names = ["wireguard/wg0.conf", "firewall/tunnelguard.nft", "audit/peer-access.json", "audit/peer-access.md"]
    first = {name: (out / name).read_bytes() for name in names}
    _, _, out, _ = run_case(workspace)
    assert first == {name: (out / name).read_bytes() for name in names}


def test_source_keeps_compiled_rust_entry_point(workspace):
    """Verify the repaired project remains a compilable Rust-delivered tool."""
    assert BIN.is_file() and os.access(BIN, os.X_OK)
    assert Path("/app/src/main.rs").read_text().strip()
