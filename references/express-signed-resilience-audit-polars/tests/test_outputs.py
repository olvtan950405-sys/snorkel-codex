"""Black-box verifier for the signed Express gateway resilience-audit service.

The verifier deliberately does not import application modules.  It starts the
public Node command, sends byte-exact HTTP requests with the timestamp/nonce/
signature admission headers, and computes successful responses with an
independent Python implementation of validation, normalization, all five
resilience rules, recursive canonical JSON, and the evidence digest.
Deterministically generated nested inventories make fixture-specific or
hard-coded solutions insufficient.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import http.client
import json
import os
import random
import re
import secrets
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_APP = Path("/app")
if not DEFAULT_APP.exists():
    DEFAULT_APP = REPOSITORY / "environment" / "app"
APP = Path(os.environ.get("APP_DIR", str(DEFAULT_APP)))
CLI = ["node", str(APP / "bin" / "security-audit.js")]
POLICY_PATH = APP / "data" / "security-policy.json"
EXAMPLE_PATH = APP / "data" / "example-bundle.json"

SECRET = "verifier-secret-π-with-utf8"
AUDIT_PATH = "/v1/audit/security-policies"
MAX_RAW_BODY_BYTES = 1_048_576
UTC_MILLIS = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$"
)


# ---------------------------------------------------------------------------
# Independent canonicalization, normalization, and policy-rule oracle.
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Return the contract's compact recursively sorted UTF-8 JSON bytes."""

    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def parse_instant(value: str) -> datetime:
    """Parse only the exact millisecond UTC timestamp grammar in the contract."""

    if not isinstance(value, str) or UTC_MILLIS.fullmatch(value) is None:
        raise ValueError(f"not an exact UTC millisecond timestamp: {value!r}")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError(f"not a real instant: {value!r}") from error
    return parsed.replace(tzinfo=timezone.utc)


def format_instant(value: datetime) -> str:
    """Format an aware datetime in the contract's exact millisecond UTC form."""

    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def normalized_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Build the exact policy evidence object used by the digest."""

    return {
        "policy_version": policy["policy_version"],
        "max_requests_per_minute": policy["max_requests_per_minute"],
        "max_timeout_ms": policy["max_timeout_ms"],
        "max_retry_attempts": policy["max_retry_attempts"],
        "require_circuit_breaker": policy["require_circuit_breaker"],
        "exempt_route_paths": sorted(set(policy["exempt_route_paths"])),
    }


def normalize_inventory(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Flatten the three evidence tables without using any application code."""

    services: list[dict[str, Any]] = []
    upstreams: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    for gateway in bundle["gateways"]:
        gateway_id = gateway["gateway_id"]
        for service in gateway["services"]:
            service_id = service["service_id"]
            services.append(
                {
                    "gateway_id": gateway_id,
                    "service_id": service_id,
                    "circuit_breaker_enabled": service["circuit_breaker"]["enabled"],
                    "rate_limit_enabled": service["rate_limit"]["enabled"],
                    "rate_limit_requests_per_minute": service["rate_limit"][
                        "requests_per_minute"
                    ],
                    "retry_max_attempts": service["retry"]["max_attempts"],
                }
            )
            for upstream in service.get("upstreams", []):
                upstreams.append(
                    {
                        "gateway_id": gateway_id,
                        "service_id": service_id,
                        "upstream_id": upstream["upstream_id"],
                        "timeout_ms": upstream["timeout_ms"],
                    }
                )
            for route in service.get("routes", []):
                routes.append(
                    {
                        "gateway_id": gateway_id,
                        "service_id": service_id,
                        "path": route["path"],
                        "rate_limit_per_minute": route["rate_limit_per_minute"],
                    }
                )

    services.sort(key=lambda row: (row["gateway_id"], row["service_id"]))
    upstreams.sort(
        key=lambda row: (row["gateway_id"], row["service_id"], row["upstream_id"])
    )
    routes.sort(key=lambda row: (row["gateway_id"], row["service_id"], row["path"]))
    return {
        "services": services,
        "upstreams": upstreams,
        "routes": routes,
    }


def evaluate_violations(
    bundle: dict[str, Any],
    policy: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Evaluate exactly the five specified resilience rules independently."""

    policy_evidence = normalized_policy(policy)
    exempt = set(policy_evidence["exempt_route_paths"])
    max_rpm = policy_evidence["max_requests_per_minute"]
    max_timeout = policy_evidence["max_timeout_ms"]
    max_retry = policy_evidence["max_retry_attempts"]
    require_cb = policy_evidence["require_circuit_breaker"]
    violations: list[dict[str, Any]] = []

    def add(
        row: dict[str, Any],
        code: str,
        severity: str,
        subject: str,
        evidence: dict[str, Any],
    ) -> None:
        violations.append(
            {
                "code": code,
                "evidence": evidence,
                "gateway_id": row["gateway_id"],
                "service_id": row["service_id"],
                "severity": severity,
                "subject": subject,
            }
        )

    for service in inventory["services"]:
        if service["rate_limit_enabled"] is False:
            add(service, "RATE_LIMIT_DISABLED", "high", "rate_limit", {"enabled": False})
        if service["retry_max_attempts"] > max_retry:
            add(
                service,
                "RETRY_BUDGET_EXCEEDED",
                "medium",
                "retry",
                {
                    "max_attempts": service["retry_max_attempts"],
                    "maximum_attempts": max_retry,
                },
            )
        if require_cb and service["circuit_breaker_enabled"] is False:
            add(
                service,
                "CIRCUIT_BREAKER_REQUIRED",
                "medium",
                "circuit_breaker",
                {"enabled": False},
            )

    for upstream in inventory["upstreams"]:
        if upstream["timeout_ms"] == 0 or upstream["timeout_ms"] > max_timeout:
            add(
                upstream,
                "UPSTREAM_TIMEOUT_UNBOUNDED",
                "critical",
                upstream["upstream_id"],
                {"maximum_ms": max_timeout, "timeout_ms": upstream["timeout_ms"]},
            )

    for route in inventory["routes"]:
        if route["path"] not in exempt and (
            route["rate_limit_per_minute"] == 0
            or route["rate_limit_per_minute"] > max_rpm
        ):
            add(
                route,
                "ROUTE_RATE_LIMIT_EXCEEDS",
                "high",
                route["path"],
                {"maximum": max_rpm, "rate_limit_per_minute": route["rate_limit_per_minute"]},
            )

    violations.sort(
        key=lambda row: (
            row["gateway_id"],
            row["service_id"],
            row["code"],
            row["subject"],
        )
    )
    return violations


def oracle_result(
    bundle: dict[str, Any], policy: dict[str, Any]
) -> tuple[dict[str, Any], bytes, bytes]:
    """Return expected payload, response bytes, and canonical digest preimage."""

    inventory = normalize_inventory(bundle)
    policy_evidence = normalized_policy(policy)
    violations = evaluate_violations(bundle, policy, inventory)
    preimage = canonical_bytes(
        {
            "audit_at": bundle["audit_at"],
            "bundle_id": bundle["bundle_id"],
            "inventory": inventory,
            "policy": policy_evidence,
            "violations": violations,
        }
    )
    payload = {
        "audit_at": bundle["audit_at"],
        "bundle_id": bundle["bundle_id"],
        "evidence_digest": hashlib.sha256(preimage).hexdigest(),
        "policy_version": policy_evidence["policy_version"],
        "service_count": len(inventory["services"]),
        "violations": violations,
    }
    return payload, canonical_bytes(payload), preimage


# ---------------------------------------------------------------------------
# Process and byte-level HTTP harness.
# ---------------------------------------------------------------------------


@dataclass
class Response:
    """Minimal captured HTTP response used by byte-exact assertions."""

    status: int
    body: bytes
    headers: list[tuple[str, str]]


@dataclass
class Server:
    """A running public CLI process and the policy it loaded."""

    process: subprocess.Popen[str]
    port: int
    secret: str
    policy: dict[str, Any]

    def stop(self) -> None:
        """Terminate the child promptly and reap it even after a failed test."""

        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def free_loopback_port() -> int:
    """Ask the kernel for a currently unused loopback port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    port: int,
    method: str,
    path: str,
    body: bytes = b"",
    headers: list[tuple[str, str]] | None = None,
    *,
    add_json_content_type: bool = True,
) -> Response:
    """Issue an HTTP request while preserving duplicate headers and raw bytes."""

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.putrequest(method, path)
        supplied_headers = headers or []
        if body or method == "POST":
            has_content_type = any(
                name.lower() == "content-type" for name, _value in supplied_headers
            )
            if add_json_content_type and not has_content_type:
                connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(body)))
        for name, value in supplied_headers:
            connection.putheader(name, value)
        connection.endheaders(body)
        raw = connection.getresponse()
        return Response(raw.status, raw.read(), raw.getheaders())
    finally:
        connection.close()


def fresh_timestamp() -> str:
    """Current wall-clock instant in the exact millisecond UTC grammar."""

    return format_instant(datetime.now(timezone.utc))


def fresh_nonce() -> str:
    """A unique 128-bit nonce rendered as 32 lowercase hexadecimal characters."""

    return secrets.token_hex(16)


def sign(timestamp: str, nonce: str, body: bytes, secret: str) -> str:
    """Compute the request signature over timestamp \\n nonce \\n body."""

    signing_input = (
        timestamp.encode("utf-8") + b"\n" + nonce.encode("utf-8") + b"\n" + body
    )
    digest = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def admission_headers(
    body: bytes,
    secret: str,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> list[tuple[str, str]]:
    """Build a fresh, correctly signed timestamp/nonce/signature header set."""

    ts = timestamp if timestamp is not None else fresh_timestamp()
    nc = nonce if nonce is not None else fresh_nonce()
    return [
        ("X-Audit-Timestamp", ts),
        ("X-Audit-Nonce", nc),
        ("X-Audit-Signature", sign(ts, nc, body, secret)),
    ]


def signed_request(
    server: Server,
    body: bytes,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
    extra_headers: list[tuple[str, str]] | None = None,
    add_json_content_type: bool = True,
) -> Response:
    """POST exact bytes with fresh admission headers plus any extra headers."""

    headers = admission_headers(body, server.secret, timestamp=timestamp, nonce=nonce)
    if extra_headers:
        headers = extra_headers + headers
    return request(
        server.port,
        "POST",
        AUDIT_PATH,
        body,
        headers,
        add_json_content_type=add_json_content_type,
    )


def response_content_type(response: Response) -> str:
    """Return the case-insensitive Content-Type response header."""

    for name, value in response.headers:
        if name.lower() == "content-type":
            return value
    return ""


def assert_exact_json(response: Response, status: int, value: Any) -> None:
    """Assert status, JSON media type, and exact canonical response bytes."""

    assert response.status == status, response.body.decode("utf-8", "replace")
    assert response.body == canonical_bytes(value)
    assert response_content_type(response).lower().startswith("application/json")


def assert_success(
    server: Server,
    bundle: dict[str, Any],
    raw_body: bytes | None = None,
) -> tuple[Response, dict[str, Any]]:
    """Compare a successful endpoint response to the independent oracle."""

    body = raw_body if raw_body is not None else canonical_bytes(bundle)
    response = signed_request(server, body)
    expected, expected_bytes, _ = oracle_result(bundle, server.policy)
    assert response.status == 200, response.body.decode("utf-8", "replace")
    assert response.body == expected_bytes
    assert response_content_type(response).lower().startswith("application/json")
    return response, expected


def start_server(
    policy_path: Path = POLICY_PATH,
    secret: str = SECRET,
    *,
    exercise_default_policy_path: bool = False,
) -> Server:
    """Start the public command on an ephemeral port and wait for health."""

    assert (APP / "bin" / "security-audit.js").is_file(), f"missing CLI under {APP}"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    last_error = "server did not become ready"
    for _attempt in range(4):
        port = free_loopback_port()
        environment = os.environ.copy()
        environment["AUDIT_HMAC_SECRET"] = secret
        if exercise_default_policy_path and APP == Path("/app"):
            environment.pop("SECURITY_POLICY_PATH", None)
        else:
            environment["SECURITY_POLICY_PATH"] = str(policy_path)
        process = subprocess.Popen(
            CLI + ["--port", str(port)],
            cwd=str(APP),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                last_error = f"server exited {process.returncode}: {stdout}{stderr}"
                break
            try:
                health = request(port, "GET", "/healthz")
            except (OSError, http.client.HTTPException):
                time.sleep(0.04)
                continue
            if health.status == 200:
                return Server(process, port, secret, policy)
            last_error = f"health returned {health.status}: {health.body!r}"
            time.sleep(0.04)
        if process.poll() is None:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=2)
            last_error = f"{last_error}; output: {stdout}{stderr}"
        if "EADDRINUSE" not in last_error:
            break
    raise AssertionError(last_error)


@pytest.fixture(scope="session")
def audit_server() -> Server:
    """Run one default-policy service for the black-box endpoint suite."""

    server = start_server(exercise_default_policy_path=True)
    yield server
    server.stop()


def run_startup_probe(environment: dict[str, str], timeout: float = 3) -> tuple[int, str, bool]:
    """Run a process expected to fail and report whether it remained alive."""

    port = free_loopback_port()
    process = subprocess.Popen(
        CLI + ["--port", str(port)],
        cwd=str(APP),
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stayed_alive = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stayed_alive = True
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=2)
    return int(process.returncode), stdout + stderr, stayed_alive


# ---------------------------------------------------------------------------
# Reusable valid fixtures and deterministic generated inventories.
# ---------------------------------------------------------------------------


def clean_service(
    policy: dict[str, Any],
    service_id: str = "service-ok",
) -> dict[str, Any]:
    """Build one compliant service for schema and mutation tests."""

    return {
        "service_id": service_id,
        "rate_limit": {"enabled": True, "requests_per_minute": 600},
        "retry": {"max_attempts": policy["max_retry_attempts"]},
        "circuit_breaker": {"enabled": True},
        "upstreams": [{"upstream_id": f"{service_id}-up", "timeout_ms": 2000}],
        "routes": [{"path": f"/{service_id}", "rate_limit_per_minute": 600}],
    }


def clean_bundle(policy: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal valid and compliant nested bundle."""

    return {
        "bundle_id": "verifier-clean",
        "audit_at": "2026-06-15T00:00:00.000Z",
        "gateways": [
            {
                "gateway_id": "gw-clean",
                "services": [clean_service(policy)],
            }
        ],
    }


def generated_bundles(policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate repeatable nested configurations spanning every rule."""

    rng = random.Random(0x5EC0A17)
    audit_at = "2026-08-20T12:34:56.789Z"
    max_rpm = policy["max_requests_per_minute"]
    max_timeout = policy["max_timeout_ms"]
    max_retry = policy["max_retry_attempts"]
    exempt = sorted(set(policy["exempt_route_paths"]))
    bundles: list[dict[str, Any]] = []
    for bundle_index in range(14):
        gateways: list[dict[str, Any]] = []
        for gateway_index in range(bundle_index % 4):
            services: list[dict[str, Any]] = []
            service_total = (bundle_index * 3 + gateway_index) % 5
            for service_index in range(service_total):
                stem = f"b{bundle_index}-g{gateway_index}-s{service_index}"
                service: dict[str, Any] = {
                    "service_id": stem,
                    "rate_limit": {
                        "enabled": rng.random() < 0.65,
                        "requests_per_minute": rng.choice([0, 100, max_rpm]),
                    },
                    "retry": {
                        "max_attempts": rng.choice(
                            [0, max_retry, max_retry + rng.randrange(1, 5)]
                        )
                    },
                    "circuit_breaker": {"enabled": rng.random() < 0.6},
                }

                upstreams: list[dict[str, Any]] = []
                for upstream_index in range(rng.randrange(4)):
                    timeout_ms = rng.choice([0, 1, max_timeout, max_timeout + 500])
                    upstreams.append(
                        {
                            "upstream_id": f"{stem}-u{upstream_index}",
                            "timeout_ms": timeout_ms,
                        }
                    )
                if upstreams or rng.random() < 0.55:
                    service["upstreams"] = upstreams

                route_entries: list[dict[str, Any]] = []
                for route_index in range(rng.randrange(4)):
                    if route_index == 0 and exempt and rng.random() < 0.3:
                        path = exempt[0]
                    else:
                        path = f"/{stem}/r{route_index}"
                    route_entries.append(
                        {
                            "path": path,
                            "rate_limit_per_minute": rng.choice([0, 200, max_rpm, max_rpm + 1000]),
                        }
                    )
                if route_entries or rng.random() < 0.55:
                    service["routes"] = route_entries
                services.append(service)
            gateways.append(
                {"gateway_id": f"generated-gw-{gateway_index}", "services": services}
            )
        bundles.append(
            {
                "bundle_id": f"generated-{bundle_index:02d}",
                "audit_at": audit_at,
                "gateways": gateways,
            }
        )
    return bundles


# ---------------------------------------------------------------------------
# Endpoint, admission, schema, rule, normalization, and digest tests.
# ---------------------------------------------------------------------------


def test_healthz_is_unsigned_canonical_and_uses_default_policy(audit_server: Server) -> None:
    """The unsigned health endpoint must expose the loaded default policy canonically."""

    response = request(audit_server.port, "GET", "/healthz")
    assert_exact_json(
        response,
        200,
        {"policy_version": audit_server.policy["policy_version"], "status": "ok"},
    )
    signed_health = request(
        audit_server.port,
        "GET",
        "/healthz",
        headers=[("X-Audit-Signature", "not-a-signature")],
    )
    assert signed_health.body == response.body
    assert signed_health.status == 200


def test_shipped_example_matches_full_reference_byte_for_byte(audit_server: Server) -> None:
    """The shipped example must produce the independently derived exact response."""

    assert EXAMPLE_PATH.is_file(), "the task must ship data/example-bundle.json"
    raw = EXAMPLE_PATH.read_bytes()
    bundle = json.loads(raw.decode("utf-8"))
    response, expected = assert_success(audit_server, bundle, raw)
    codes = [violation["code"] for violation in expected["violations"]]
    assert codes == [
        "CIRCUIT_BREAKER_REQUIRED",
        "RATE_LIMIT_DISABLED",
        "RETRY_BUDGET_EXCEEDED",
        "ROUTE_RATE_LIMIT_EXCEEDS",
        "UPSTREAM_TIMEOUT_UNBOUNDED",
    ]
    assert len(expected["evidence_digest"]) == 64
    assert response.body.endswith(b"\n") and not response.body.endswith(b"\n\n")


def test_generated_nested_bundles_match_independent_property_oracle(
    audit_server: Server,
) -> None:
    """Generated multi-level inventories must match the Python oracle exactly."""

    cases = generated_bundles(audit_server.policy)
    assert any(len(case["gateways"]) >= 3 for case in cases)
    assert any(
        len(gateway["services"]) >= 3
        for case in cases
        for gateway in case["gateways"]
    )
    for case in cases:
        response, _ = assert_success(audit_server, case)
        assert response.body.count(b"evidence_digest") == 1, case["bundle_id"]


def test_hmac_covers_exact_wire_bytes_while_json_formatting_normalizes(
    audit_server: Server,
) -> None:
    """Valid signatures cover raw bytes, while equivalent JSON yields equal output."""

    bundle = clean_bundle(audit_server.policy)
    compact = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pretty = json.dumps(bundle, ensure_ascii=False, indent=3).encode("utf-8") + b"\n"
    reordered = json.dumps(
        {"gateways": bundle["gateways"], "audit_at": bundle["audit_at"], "bundle_id": bundle["bundle_id"]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    compact_response = signed_request(audit_server, compact)
    pretty_response = signed_request(audit_server, pretty)
    reordered_response = signed_request(audit_server, reordered)
    expected = oracle_result(bundle, audit_server.policy)[1]
    assert compact_response.body == pretty_response.body == reordered_response.body == expected
    assert compact_response.status == pretty_response.status == reordered_response.status == 200

    # A signature computed over the compact bytes must not authenticate the
    # pretty bytes, even with a matching timestamp and nonce in the input.
    timestamp = fresh_timestamp()
    nonce = fresh_nonce()
    wrong_raw_signature = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        pretty,
        [
            ("X-Audit-Timestamp", timestamp),
            ("X-Audit-Nonce", nonce),
            ("X-Audit-Signature", sign(timestamp, nonce, compact, audit_server.secret)),
        ],
    )
    assert_exact_json(wrong_raw_signature, 401, {"error": "invalid_signature"})


def test_raw_body_limit_accepts_equality_and_rejects_excess(
    audit_server: Server,
) -> None:
    """The streaming byte limit accepts exactly 1 MiB and rejects one byte more."""

    def padded(size: int) -> tuple[dict[str, Any], bytes]:
        bundle = {
            "bundle_id": "body-limit",
            "audit_at": "2026-06-15T00:00:00.000Z",
            "gateways": [],
            "ignored_padding": "",
        }
        empty = canonical_bytes(bundle)
        padding_length = size - len(empty)
        assert padding_length >= 0
        bundle["ignored_padding"] = "x" * padding_length
        body = canonical_bytes(bundle)
        assert len(body) == size
        return bundle, body

    exact_bundle, exact_body = padded(MAX_RAW_BODY_BYTES)
    assert_success(audit_server, exact_bundle, exact_body)

    _oversized_bundle, oversized_body = padded(MAX_RAW_BODY_BYTES + 1)
    assert_exact_json(
        signed_request(audit_server, oversized_body),
        413,
        {"error": "payload_too_large"},
    )
    unauthenticated = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        oversized_body,
        [("X-Audit-Signature", "sha256=" + "0" * 64)],
    )
    assert_exact_json(unauthenticated, 413, {"error": "payload_too_large"})


def test_signature_failure_forms_are_uniform_and_strict(audit_server: Server) -> None:
    """Missing, malformed, uppercase, and incorrect signatures must all be 401."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    timestamp = fresh_timestamp()
    nonce = fresh_nonce()
    valid = sign(timestamp, nonce, body, audit_server.secret)
    digest = valid.removeprefix("sha256=")
    malformed = [
        None,
        "",
        digest,
        f"SHA256={digest}",
        f"sha256={digest.upper()}",
        f"sha256={digest[:-1]}",
        f"sha256={digest}0",
        "sha256=" + "g" * 64,
        f"sha256={digest}:suffix",
        "sha256=" + ("0" * 64 if digest != "0" * 64 else "1" * 64),
        f"{valid},{valid}",
    ]
    for value in malformed:
        headers = [
            ("X-Audit-Timestamp", timestamp),
            ("X-Audit-Nonce", fresh_nonce()),
        ]
        if value is not None:
            headers.append(("X-Audit-Signature", value))
        response = request(audit_server.port, "POST", AUDIT_PATH, body, headers)
        assert_exact_json(response, 401, {"error": "invalid_signature"})


def test_malformed_or_duplicate_admission_headers_are_401(audit_server: Server) -> None:
    """Bad timestamp/nonce forms and any duplicated admission field are rejected."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    good_ts = fresh_timestamp()

    bad_timestamps = [
        None,
        "",
        "2026-06-15T00:00:00Z",
        "2026-06-15T00:00:00.000+00:00",
        "2026-13-01T00:00:00.000Z",
        "not-a-time",
    ]
    for value in bad_timestamps:
        nonce = fresh_nonce()
        headers = [("X-Audit-Nonce", nonce)]
        if value is not None:
            headers.append(("X-Audit-Timestamp", value))
        headers.append(("X-Audit-Signature", sign(value or "", nonce, body, audit_server.secret)))
        assert_exact_json(
            request(audit_server.port, "POST", AUDIT_PATH, body, headers),
            401,
            {"error": "invalid_signature"},
        )

    bad_nonces = [
        None,
        "",
        "0" * 31,
        "0" * 33,
        "0" * 63 + "Z",
        secrets.token_hex(16).upper(),
        "not-hex-" + "0" * 24,
    ]
    for value in bad_nonces:
        headers = [("X-Audit-Timestamp", good_ts)]
        if value is not None:
            headers.append(("X-Audit-Nonce", value))
        headers.append(("X-Audit-Signature", sign(good_ts, value or "", body, audit_server.secret)))
        assert_exact_json(
            request(audit_server.port, "POST", AUDIT_PATH, body, headers),
            401,
            {"error": "invalid_signature"},
        )

    # Duplicate physical field lines for any admission header are invalid.
    nonce = fresh_nonce()
    signature = sign(good_ts, nonce, body, audit_server.secret)
    duplicate_sets = [
        [("X-Audit-Timestamp", good_ts), ("X-Audit-Timestamp", good_ts), ("X-Audit-Nonce", nonce), ("X-Audit-Signature", signature)],
        [("X-Audit-Timestamp", good_ts), ("X-Audit-Nonce", nonce), ("X-Audit-Nonce", nonce), ("X-Audit-Signature", signature)],
        [("X-Audit-Timestamp", good_ts), ("X-Audit-Nonce", nonce), ("X-Audit-Signature", signature), ("X-Audit-Signature", signature)],
    ]
    for headers in duplicate_sets:
        assert_exact_json(
            request(audit_server.port, "POST", AUDIT_PATH, body, headers),
            401,
            {"error": "invalid_signature"},
        )


def test_signature_binds_timestamp_and_nonce(audit_server: Server) -> None:
    """Tampering with the timestamp or nonce after signing must break the MAC."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    timestamp = fresh_timestamp()
    nonce = fresh_nonce()
    signature = sign(timestamp, nonce, body, audit_server.secret)

    tampered_nonce = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [
            ("X-Audit-Timestamp", timestamp),
            ("X-Audit-Nonce", fresh_nonce()),
            ("X-Audit-Signature", signature),
        ],
    )
    assert_exact_json(tampered_nonce, 401, {"error": "invalid_signature"})

    tampered_timestamp = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [
            ("X-Audit-Timestamp", format_instant(datetime.now(timezone.utc) + timedelta(seconds=1))),
            ("X-Audit-Nonce", nonce),
            ("X-Audit-Signature", signature),
        ],
    )
    assert_exact_json(tampered_timestamp, 401, {"error": "invalid_signature"})


def test_stale_and_future_timestamps_are_rejected_after_authentication(
    audit_server: Server,
) -> None:
    """A correctly signed request outside the clock-skew window is not admitted."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    past = format_instant(datetime.now(timezone.utc) - timedelta(hours=1))
    future = format_instant(datetime.now(timezone.utc) + timedelta(hours=1))
    for stale in (past, future):
        assert_exact_json(
            signed_request(audit_server, body, timestamp=stale),
            401,
            {"error": "stale_request"},
        )


def test_replayed_nonce_is_rejected_after_first_use(audit_server: Server) -> None:
    """A nonce accepted once must be refused on any later fresh, valid request."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    timestamp = fresh_timestamp()
    nonce = fresh_nonce()
    headers = [
        ("X-Audit-Timestamp", timestamp),
        ("X-Audit-Nonce", nonce),
        ("X-Audit-Signature", sign(timestamp, nonce, body, audit_server.secret)),
    ]
    first = request(audit_server.port, "POST", AUDIT_PATH, body, headers)
    assert first.status == 200, first.body.decode("utf-8", "replace")
    second = request(audit_server.port, "POST", AUDIT_PATH, body, headers)
    assert_exact_json(second, 401, {"error": "replayed_request"})

    # A different, correctly signed body under the same nonce is still a replay.
    other_body = canonical_bytes(
        {**clean_bundle(audit_server.policy), "bundle_id": "verifier-clean-2"}
    )
    other_ts = fresh_timestamp()
    reused = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        other_body,
        [
            ("X-Audit-Timestamp", other_ts),
            ("X-Audit-Nonce", nonce),
            ("X-Audit-Signature", sign(other_ts, nonce, other_body, audit_server.secret)),
        ],
    )
    assert_exact_json(reused, 401, {"error": "replayed_request"})


def test_authentication_precedes_json_parsing_and_bundle_validation(
    audit_server: Server,
) -> None:
    """Unauthenticated malformed JSON and invalid schemas must not reveal details."""

    good_ts = fresh_timestamp()
    for body in [b'{"unterminated":', b"null", b'{"bundle_id":""}']:
        response = request(
            audit_server.port,
            "POST",
            AUDIT_PATH,
            body,
            [
                ("X-Audit-Timestamp", good_ts),
                ("X-Audit-Nonce", fresh_nonce()),
                ("X-Audit-Signature", "sha256=" + "0" * 64),
            ],
        )
        assert_exact_json(response, 401, {"error": "invalid_signature"})


def test_content_encoding_and_media_type_are_checked_after_admission(
    audit_server: Server,
) -> None:
    """Encoding and JSON media type checks occur only after admission."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    for extra, add_default in [
        ([('Content-Type', 'text/plain')], True),
        ([], False),
    ]:
        response = signed_request(
            audit_server,
            body,
            extra_headers=extra,
            add_json_content_type=add_default,
        )
        assert_exact_json(response, 415, {"error": "unsupported_media_type"})

    unauthenticated = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [("X-Audit-Signature", "sha256=" + "0" * 64), ("Content-Type", "text/plain")],
    )
    assert_exact_json(unauthenticated, 401, {"error": "invalid_signature"})

    encoded = signed_request(audit_server, body, extra_headers=[("Content-Encoding", "gzip")])
    assert_exact_json(encoded, 415, {"error": "unsupported_content_encoding"})
    identity = signed_request(audit_server, body, extra_headers=[("Content-Encoding", "identity")])
    assert identity.status == 200
    parameterized_json = signed_request(
        audit_server,
        body,
        extra_headers=[("Content-Type", "Application/JSON; charset=utf-8")],
    )
    assert parameterized_json.status == 200


def test_correctly_signed_invalid_json_and_invalid_utf8_are_400(
    audit_server: Server,
) -> None:
    """Signed syntax errors and replacement-parseable invalid UTF-8 must be invalid_json."""

    bodies = [
        b"",
        b'{"unterminated":',
        b'{"valid":true} trailing',
        b'{"x":"\xff"}',
        b"\xff",
    ]
    for body in bodies:
        assert_exact_json(signed_request(audit_server, body), 400, {"error": "invalid_json"})


def invalid_bundle_cases(policy: dict[str, Any]) -> list[tuple[str, Any]]:
    """Construct schema mutations covering every stated type and uniqueness rule."""

    base = clean_bundle(policy)
    cases: list[tuple[str, Any]] = [
        ("null", None),
        ("array", []),
        ("string", "bundle"),
        ("empty object", {}),
    ]

    def add(name: str, mutate: Any) -> None:
        candidate = copy.deepcopy(base)
        mutate(candidate)
        cases.append((name, candidate))

    def svc(value: Any) -> Any:
        return value["gateways"][0]["services"][0]

    def up(value: Any) -> Any:
        return svc(value)["upstreams"][0]

    def rt(value: Any) -> Any:
        return svc(value)["routes"][0]

    add("missing bundle_id", lambda value: value.pop("bundle_id"))
    add("empty bundle_id", lambda value: value.__setitem__("bundle_id", ""))
    add("non-string bundle_id", lambda value: value.__setitem__("bundle_id", 7))
    add("non-scalar bundle_id", lambda value: value.__setitem__("bundle_id", "\ud800"))
    add("missing audit_at", lambda value: value.pop("audit_at"))
    for label, timestamp in [
        ("no milliseconds", "2026-06-15T00:00:00Z"),
        ("offset timestamp", "2026-06-15T00:00:00.000+00:00"),
        ("too many fractional digits", "2026-06-15T00:00:00.0000Z"),
        ("impossible day", "2026-02-30T00:00:00.000Z"),
        ("impossible hour", "2026-06-15T24:00:00.000Z"),
    ]:
        add(label, lambda value, ts=timestamp: value.__setitem__("audit_at", ts))
    add("gateways missing", lambda value: value.pop("gateways"))
    add("gateways non-array", lambda value: value.__setitem__("gateways", {}))
    add("gateway non-object", lambda value: value["gateways"].__setitem__(0, []))
    add("gateway id missing", lambda value: value["gateways"][0].pop("gateway_id"))
    add("gateway id empty", lambda value: value["gateways"][0].__setitem__("gateway_id", ""))
    add("gateway id non-string", lambda value: value["gateways"][0].__setitem__("gateway_id", 9))
    add("services missing", lambda value: value["gateways"][0].pop("services"))
    add("services non-array", lambda value: value["gateways"][0].__setitem__("services", {}))
    add("service non-object", lambda value: value["gateways"][0]["services"].__setitem__(0, None))
    add("service id missing", lambda value: svc(value).pop("service_id"))
    add("service id empty", lambda value: svc(value).__setitem__("service_id", ""))
    add("service id non-string", lambda value: svc(value).__setitem__("service_id", False))
    add("rate_limit missing", lambda value: svc(value).pop("rate_limit"))
    add("rate_limit non-object", lambda value: svc(value).__setitem__("rate_limit", []))
    add("rate_limit enabled missing", lambda value: svc(value)["rate_limit"].pop("enabled"))
    add("rate_limit enabled non-boolean", lambda value: svc(value)["rate_limit"].__setitem__("enabled", "true"))
    add("rate_limit rpm missing", lambda value: svc(value)["rate_limit"].pop("requests_per_minute"))
    add("rate_limit rpm non-integer", lambda value: svc(value)["rate_limit"].__setitem__("requests_per_minute", 1.5))
    add("rate_limit rpm negative", lambda value: svc(value)["rate_limit"].__setitem__("requests_per_minute", -1))
    add("rate_limit rpm too large", lambda value: svc(value)["rate_limit"].__setitem__("requests_per_minute", 1_000_000_001))
    add("rate_limit rpm non-number", lambda value: svc(value)["rate_limit"].__setitem__("requests_per_minute", "600"))
    add("retry missing", lambda value: svc(value).pop("retry"))
    add("retry non-object", lambda value: svc(value).__setitem__("retry", []))
    add("retry max_attempts missing", lambda value: svc(value)["retry"].pop("max_attempts"))
    add("retry max_attempts non-integer", lambda value: svc(value)["retry"].__setitem__("max_attempts", 2.5))
    add("retry max_attempts negative", lambda value: svc(value)["retry"].__setitem__("max_attempts", -1))
    add("retry max_attempts too large", lambda value: svc(value)["retry"].__setitem__("max_attempts", 1_000_001))
    add("circuit_breaker missing", lambda value: svc(value).pop("circuit_breaker"))
    add("circuit_breaker non-object", lambda value: svc(value).__setitem__("circuit_breaker", None))
    add("circuit_breaker enabled missing", lambda value: svc(value)["circuit_breaker"].pop("enabled"))
    add("circuit_breaker enabled non-boolean", lambda value: svc(value)["circuit_breaker"].__setitem__("enabled", 1))
    add("upstreams non-array", lambda value: svc(value).__setitem__("upstreams", {}))
    add("upstream non-object", lambda value: svc(value).__setitem__("upstreams", [None]))
    add("upstream id missing", lambda value: up(value).pop("upstream_id"))
    add("upstream id empty", lambda value: up(value).__setitem__("upstream_id", ""))
    add("upstream id non-string", lambda value: up(value).__setitem__("upstream_id", 2))
    add("upstream timeout missing", lambda value: up(value).pop("timeout_ms"))
    add("upstream timeout non-integer", lambda value: up(value).__setitem__("timeout_ms", 1.5))
    add("upstream timeout negative", lambda value: up(value).__setitem__("timeout_ms", -1))
    add("upstream timeout too large", lambda value: up(value).__setitem__("timeout_ms", 1_000_000_001))
    add("upstream timeout non-number", lambda value: up(value).__setitem__("timeout_ms", "2000"))
    add("routes non-array", lambda value: svc(value).__setitem__("routes", {}))
    add("route non-object", lambda value: svc(value).__setitem__("routes", [None]))
    add("route path missing", lambda value: rt(value).pop("path"))
    add("route path empty", lambda value: rt(value).__setitem__("path", ""))
    add("route path non-string", lambda value: rt(value).__setitem__("path", []))
    add("route path non-scalar", lambda value: rt(value).__setitem__("path", "\udfff"))
    add("route rpm missing", lambda value: rt(value).pop("rate_limit_per_minute"))
    add("route rpm non-integer", lambda value: rt(value).__setitem__("rate_limit_per_minute", 3.5))
    add("route rpm negative", lambda value: rt(value).__setitem__("rate_limit_per_minute", -5))
    add("route rpm too large", lambda value: rt(value).__setitem__("rate_limit_per_minute", 1_000_000_001))
    add("route rpm non-number", lambda value: rt(value).__setitem__("rate_limit_per_minute", "600"))

    duplicate_gateway = copy.deepcopy(base["gateways"][0])
    add("duplicate gateway id", lambda value: value["gateways"].append(duplicate_gateway))
    duplicate_service = copy.deepcopy(base["gateways"][0]["services"][0])
    add("duplicate service id within gateway", lambda value: value["gateways"][0]["services"].append(duplicate_service))
    duplicate_upstream = copy.deepcopy(base["gateways"][0]["services"][0]["upstreams"][0])
    add("duplicate upstream id within service", lambda value: svc(value)["upstreams"].append(duplicate_upstream))
    duplicate_route = copy.deepcopy(base["gateways"][0]["services"][0]["routes"][0])
    add("duplicate route path within service", lambda value: svc(value)["routes"].append(duplicate_route))
    return cases


def test_correctly_signed_schema_violation_matrix_is_422(audit_server: Server) -> None:
    """Every specified nested type, value, integer, boolean, and uniqueness error is 422."""

    for name, bundle in invalid_bundle_cases(audit_server.policy):
        body = (
            json.dumps(bundle, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            + "\n"
        ).encode("ascii")
        response = signed_request(audit_server, body)
        assert response.status == 422, f"{name}: {response.status} {response.body!r}"
        assert response.body == canonical_bytes({"error": "invalid_bundle"}), name


def test_uniqueness_scopes_optional_arrays(audit_server: Server) -> None:
    """Optional lists default empty while IDs may repeat only across allowed scopes."""

    service_one = {
        "service_id": "shared-service-id",
        "rate_limit": {"enabled": True, "requests_per_minute": 100},
        "retry": {"max_attempts": 0},
        "circuit_breaker": {"enabled": True},
    }
    service_two = copy.deepcopy(service_one)
    service_three = copy.deepcopy(service_one)
    service_three["service_id"] = "different-service-id"
    bundle = {
        "bundle_id": "scope-and-optionals",
        "audit_at": "2026-06-15T00:00:00.000Z",
        "gateways": [
            {"gateway_id": "gw-a", "services": [service_one, service_three]},
            {"gateway_id": "gw-b", "services": [service_two]},
        ],
    }
    _, expected = assert_success(audit_server, bundle)
    assert expected["service_count"] == 3
    assert expected["violations"] == []


def test_all_five_rules_obey_strict_boundaries_and_exemptions(
    audit_server: Server,
) -> None:
    """Zero, equality, and just-over cases for every rule must yield exact records."""

    policy = audit_server.policy
    max_rpm = policy["max_requests_per_minute"]
    max_timeout = policy["max_timeout_ms"]
    max_retry = policy["max_retry_attempts"]
    exempt = sorted(set(policy["exempt_route_paths"]))[0]

    boundary = {
        "service_id": "boundary",
        "rate_limit": {"enabled": True, "requests_per_minute": 600},
        "retry": {"max_attempts": max_retry + 1},
        "circuit_breaker": {"enabled": True},
        "upstreams": [
            {"upstream_id": "u-zero", "timeout_ms": 0},
            {"upstream_id": "u-max", "timeout_ms": max_timeout},
            {"upstream_id": "u-over", "timeout_ms": max_timeout + 1},
        ],
        "routes": [
            {"path": "/zero", "rate_limit_per_minute": 0},
            {"path": "/max", "rate_limit_per_minute": max_rpm},
            {"path": "/over", "rate_limit_per_minute": max_rpm + 1},
            {"path": exempt, "rate_limit_per_minute": 0},
        ],
    }
    toggles = {
        "service_id": "toggles",
        "rate_limit": {"enabled": False, "requests_per_minute": 100},
        "retry": {"max_attempts": max_retry},
        "circuit_breaker": {"enabled": False},
        "upstreams": [{"upstream_id": "ok", "timeout_ms": 1}],
        "routes": [{"path": "/ok", "rate_limit_per_minute": 1}],
    }
    bundle = {
        "bundle_id": "all-rule-boundaries",
        "audit_at": "2026-06-15T00:00:00.000Z",
        "gateways": [{"gateway_id": "gw-rules", "services": [boundary, toggles]}],
    }
    _, expected = assert_success(audit_server, bundle)
    triples = [
        (item["service_id"], item["code"], item["subject"])
        for item in expected["violations"]
    ]
    assert triples == [
        ("boundary", "RETRY_BUDGET_EXCEEDED", "retry"),
        ("boundary", "ROUTE_RATE_LIMIT_EXCEEDS", "/over"),
        ("boundary", "ROUTE_RATE_LIMIT_EXCEEDS", "/zero"),
        ("boundary", "UPSTREAM_TIMEOUT_UNBOUNDED", "u-over"),
        ("boundary", "UPSTREAM_TIMEOUT_UNBOUNDED", "u-zero"),
        ("toggles", "CIRCUIT_BREAKER_REQUIRED", "circuit_breaker"),
        ("toggles", "RATE_LIMIT_DISABLED", "rate_limit"),
    ]
    retry = next(item for item in expected["violations"] if item["code"] == "RETRY_BUDGET_EXCEEDED")
    assert retry["evidence"] == {"max_attempts": max_retry + 1, "maximum_attempts": max_retry}
    zero_timeout = next(
        item
        for item in expected["violations"]
        if item["code"] == "UPSTREAM_TIMEOUT_UNBOUNDED" and item["subject"] == "u-zero"
    )
    assert zero_timeout["evidence"] == {"maximum_ms": max_timeout, "timeout_ms": 0}
    over_route = next(
        item
        for item in expected["violations"]
        if item["code"] == "ROUTE_RATE_LIMIT_EXCEEDS" and item["subject"] == "/over"
    )
    assert over_route["evidence"] == {"maximum": max_rpm, "rate_limit_per_minute": max_rpm + 1}


def test_zero_length_gateway_service_and_child_arrays_are_supported(
    audit_server: Server,
) -> None:
    """All documented arrays may be empty without crashes or phantom rows."""

    empty_gateways = {
        "bundle_id": "empty-gateways",
        "audit_at": "2026-06-15T00:00:00.000Z",
        "gateways": [],
    }
    _, expected = assert_success(audit_server, empty_gateways)
    assert expected["service_count"] == 0 and expected["violations"] == []

    empty_services = copy.deepcopy(empty_gateways)
    empty_services["bundle_id"] = "empty-services"
    empty_services["gateways"] = [{"gateway_id": "empty-gw", "services": []}]
    _, expected = assert_success(audit_server, empty_services)
    assert expected["service_count"] == 0 and expected["violations"] == []

    empty_children = copy.deepcopy(empty_gateways)
    empty_children["bundle_id"] = "empty-children"
    empty_children["gateways"] = [
        {
            "gateway_id": "gw",
            "services": [
                {
                    "service_id": "svc",
                    "rate_limit": {"enabled": True, "requests_per_minute": 100},
                    "retry": {"max_attempts": 0},
                    "circuit_breaker": {"enabled": False},
                    "upstreams": [],
                    "routes": [],
                }
            ],
        }
    ]
    _, expected = assert_success(audit_server, empty_children)
    assert expected["service_count"] == 1
    assert [row["code"] for row in expected["violations"]] == [
        "CIRCUIT_BREAKER_REQUIRED"
    ]


def recursively_reverse_objects(value: Any) -> Any:
    """Rebuild mappings with reverse insertion order for wire-order tests."""

    if isinstance(value, dict):
        return {
            key: recursively_reverse_objects(value[key])
            for key in reversed(list(value.keys()))
        }
    if isinstance(value, list):
        return [recursively_reverse_objects(item) for item in value]
    return value


def test_permutation_whitespace_and_key_order_are_invariant(
    audit_server: Server,
) -> None:
    """Declared non-semantic ordering and formatting changes preserve response bytes."""

    policy = audit_server.policy
    services: list[dict[str, Any]] = []
    for index in range(4):
        service = clean_service(policy, f"permuted-{index}")
        service["upstreams"].append(
            {"upstream_id": f"permuted-{index}-up-b", "timeout_ms": 3000}
        )
        service["routes"].append(
            {"path": f"/permuted-{index}/b", "rate_limit_per_minute": 300}
        )
        services.append(service)
    original = {
        "bundle_id": "permutation-invariance",
        "audit_at": "2026-06-15T00:00:00.000Z",
        "gateways": [
            {"gateway_id": "gw-z", "services": services[:2]},
            {"gateway_id": "gw-a", "services": services[2:]},
        ],
    }
    variant = recursively_reverse_objects(copy.deepcopy(original))
    variant["ignored_extension"] = {"does_not_enter": "evidence"}
    variant["gateways"].reverse()
    for gateway in variant["gateways"]:
        gateway["ignored_gateway_field"] = True
        gateway["services"].reverse()
        for service in gateway["services"]:
            service["rate_limit"]["ignored_rate_field"] = [1, 2, 3]
            service["upstreams"].reverse()
            service["routes"].reverse()

    original_raw = json.dumps(original, ensure_ascii=False, indent=2).encode("utf-8")
    variant_raw = json.dumps(variant, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    original_response, _ = assert_success(audit_server, original, original_raw)
    variant_response, _ = assert_success(audit_server, variant, variant_raw)
    assert original_response.body == variant_response.body


def test_semantic_inventory_change_changes_digest_even_without_rule_change(
    audit_server: Server,
) -> None:
    """A compliant inventory-field edit must affect the evidence digest preimage."""

    original = clean_bundle(audit_server.policy)
    changed = copy.deepcopy(original)
    changed["gateways"][0]["services"][0]["rate_limit"]["requests_per_minute"] = 700
    _, first = assert_success(audit_server, original)
    _, second = assert_success(audit_server, changed)
    assert first["violations"] == second["violations"] == []
    assert first["evidence_digest"] != second["evidence_digest"]


def test_custom_runtime_policy_drives_health_rules_and_digest(
    tmp_path: Path,
) -> None:
    """A selected policy file, including allowlist dedup and toggle, must replace defaults."""

    custom_policy = {
        "exempt_route_paths": ["/metrics", "/metrics"],
        "require_circuit_breaker": False,
        "max_requests_per_minute": 100,
        "max_timeout_ms": 500,
        "max_retry_attempts": 1,
        "policy_version": "CUSTOM-π-2026",
    }
    path = tmp_path / "custom-policy.json"
    path.write_bytes(canonical_bytes(custom_policy))
    server = start_server(path, secret="custom-policy-secret")
    try:
        assert_exact_json(
            request(server.port, "GET", "/healthz"),
            200,
            {"policy_version": "CUSTOM-π-2026", "status": "ok"},
        )
        service = {
            "service_id": "custom-rules",
            "rate_limit": {"enabled": False, "requests_per_minute": 50},
            "retry": {"max_attempts": 5},
            "circuit_breaker": {"enabled": False},
            "upstreams": [{"upstream_id": "u", "timeout_ms": 1000}],
            "routes": [
                {"path": "/api", "rate_limit_per_minute": 1000},
                {"path": "/metrics", "rate_limit_per_minute": 0},
            ],
        }
        bundle = {
            "bundle_id": "custom-policy-bundle",
            "audit_at": "2026-06-15T00:00:00.000Z",
            "gateways": [{"gateway_id": "custom-gw", "services": [service]}],
        }
        _, expected = assert_success(server, bundle)
        assert expected["policy_version"] == "CUSTOM-π-2026"
        assert [(row["code"], row["subject"]) for row in expected["violations"]] == [
            ("RATE_LIMIT_DISABLED", "rate_limit"),
            ("RETRY_BUDGET_EXCEEDED", "retry"),
            ("ROUTE_RATE_LIMIT_EXCEEDS", "/api"),
            ("UPSTREAM_TIMEOUT_UNBOUNDED", "u"),
        ]
    finally:
        server.stop()


def test_recursive_utf8_canonical_bytes_and_digest_preimage(audit_server: Server) -> None:
    """Non-ASCII evidence must remain UTF-8 and hash the exact newline-terminated preimage."""

    policy = audit_server.policy
    bundle = clean_bundle(policy)
    bundle["bundle_id"] = "snapshot-雪-π"
    bundle["gateways"][0]["gateway_id"] = "网关"
    service = bundle["gateways"][0]["services"][0]
    service["service_id"] = "serviço"
    service["upstreams"] = [
        {"upstream_id": "上游", "timeout_ms": 0},
        {"upstream_id": "", "timeout_ms": 0},
        {"upstream_id": "\U00010000", "timeout_ms": 0},
    ]
    service["routes"] = []
    raw = json.dumps(bundle, ensure_ascii=True, indent=1).encode("ascii")
    response, expected = assert_success(audit_server, bundle, raw)
    payload, expected_bytes, preimage = oracle_result(bundle, policy)
    assert response.body == expected_bytes
    assert "snapshot-雪-π".encode("utf-8") in response.body
    assert b"snapshot-\\u96ea" not in response.body
    assert preimage.endswith(b"\n") and not preimage.endswith(b"\n\n")
    assert expected["evidence_digest"] == hashlib.sha256(preimage).hexdigest()
    assert payload["evidence_digest"] == expected["evidence_digest"]
    subjects = [
        row["subject"]
        for row in expected["violations"]
        if row["code"] == "UPSTREAM_TIMEOUT_UNBOUNDED"
    ]
    assert subjects == sorted(["上游", "", "\U00010000"])


# ---------------------------------------------------------------------------
# Startup and tool/security-specific implementation requirements.
# ---------------------------------------------------------------------------


def test_startup_requires_a_nonempty_utf8_hmac_secret() -> None:
    """Both unset and empty AUDIT_HMAC_SECRET must fail fast with the required message."""

    for secret_value in [None, ""]:
        environment = os.environ.copy()
        environment["SECURITY_POLICY_PATH"] = str(POLICY_PATH)
        environment.pop("AUDIT_MAX_CLOCK_SKEW_MS", None)
        if secret_value is None:
            environment.pop("AUDIT_HMAC_SECRET", None)
        else:
            environment["AUDIT_HMAC_SECRET"] = secret_value
        returncode, output, stayed_alive = run_startup_probe(environment)
        assert not stayed_alive, "server remained alive without a usable secret"
        assert returncode != 0
        assert "AUDIT_HMAC_SECRET is required" in output


def test_startup_rejects_a_malformed_clock_skew_window() -> None:
    """A present but non-integer, negative, or out-of-range skew must be fatal."""

    for skew_value in ["not-an-int", "-5", "1.5", "99999999999"]:
        environment = os.environ.copy()
        environment["AUDIT_HMAC_SECRET"] = SECRET
        environment["SECURITY_POLICY_PATH"] = str(POLICY_PATH)
        environment["AUDIT_MAX_CLOCK_SKEW_MS"] = skew_value
        returncode, _output, stayed_alive = run_startup_probe(environment)
        assert not stayed_alive, f"server accepted malformed skew {skew_value!r}"
        assert returncode != 0, f"server accepted malformed skew {skew_value!r}"


def test_startup_fails_when_selected_policy_cannot_be_loaded_or_validated(
    tmp_path: Path,
) -> None:
    """Missing, malformed, and structurally invalid policy files must be fatal."""

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"policy_version":"only-one-field"}', encoding="utf-8")
    oversized_timeout = tmp_path / "oversized-timeout.json"
    oversized_timeout.write_bytes(
        canonical_bytes(
            {
                "policy_version": "oversized",
                "max_requests_per_minute": 6000,
                "max_timeout_ms": 1_000_000_001,
                "max_retry_attempts": 3,
                "require_circuit_breaker": True,
                "exempt_route_paths": ["/metrics"],
            }
        )
    )
    zero_timeout = tmp_path / "zero-timeout.json"
    zero_timeout.write_bytes(
        canonical_bytes(
            {
                "policy_version": "zero-timeout",
                "max_requests_per_minute": 6000,
                "max_timeout_ms": 0,
                "max_retry_attempts": 3,
                "require_circuit_breaker": True,
                "exempt_route_paths": ["/metrics"],
            }
        )
    )
    bad_boolean = tmp_path / "bad-boolean.json"
    bad_boolean.write_bytes(
        canonical_bytes(
            {
                "policy_version": "bad-boolean",
                "max_requests_per_minute": 6000,
                "max_timeout_ms": 30000,
                "max_retry_attempts": 3,
                "require_circuit_breaker": "yes",
                "exempt_route_paths": ["/metrics"],
            }
        )
    )
    non_scalar = tmp_path / "non-scalar-policy.json"
    non_scalar.write_text(
        '{"exempt_route_paths":["\\ud800"],"max_requests_per_minute":6000,'
        '"max_retry_attempts":3,"max_timeout_ms":30000,"policy_version":"invalid",'
        '"require_circuit_breaker":true}\n',
        encoding="ascii",
    )
    for path in [
        tmp_path / "does-not-exist.json",
        malformed,
        invalid,
        oversized_timeout,
        zero_timeout,
        bad_boolean,
        non_scalar,
    ]:
        environment = os.environ.copy()
        environment["AUDIT_HMAC_SECRET"] = SECRET
        environment["SECURITY_POLICY_PATH"] = str(path)
        returncode, _output, stayed_alive = run_startup_probe(environment)
        assert not stayed_alive, f"server accepted invalid policy {path}"
        assert returncode != 0, f"server accepted invalid policy {path}"


def strip_javascript_comments(source: str) -> str:
    """Remove ordinary comments before checking required active call syntax."""

    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", without_blocks)


def test_required_polars_and_constant_time_primitives_are_active_in_source() -> None:
    """Source must actively call Polars DataFrame/explode and crypto timingSafeEqual."""

    paths = sorted((APP / "src").rglob("*.js"))
    assert paths, f"no JavaScript source found under {APP / 'src'}"
    active_source = "\n".join(
        strip_javascript_comments(path.read_text(encoding="utf-8")) for path in paths
    )
    assert re.search(r"(?:from\s+|require\s*\(\s*)['\"]nodejs-polars['\"]", active_source), (
        "normalization must import nodejs-polars"
    )
    assert re.search(r"\bDataFrame\s*\(", active_source), (
        "normalization must construct a nodejs-polars DataFrame"
    )
    explode_calls = re.findall(r"\.explode\s*\(", active_source)
    assert len(explode_calls) >= 3, (
        "services, upstreams, and routes each require a Polars explode"
    )
    assert re.search(r"\btimingSafeEqual\s*\(", active_source), (
        "well-formed HMAC bytes must be compared with crypto.timingSafeEqual"
    )
