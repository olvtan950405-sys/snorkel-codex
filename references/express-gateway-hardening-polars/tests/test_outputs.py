"""Black-box verifier for the signed Express gateway security-audit service.

The verifier deliberately does not import application modules.  It starts the
public Node command, sends byte-exact HTTP requests, and computes successful
responses with an independent Python implementation of validation,
normalization, all five rules, recursive canonical JSON, and the evidence
digest.  Deterministically generated nested inventories make fixture-specific
or hard-coded solutions insufficient.
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
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
TLS_VERSIONS = ["TLSv1.0", "TLSv1.1", "TLSv1.2", "TLSv1.3"]
KEY_TYPES = ["EC", "Ed25519", "RSA"]
AUTHENTICATION_MODES = ["api_key", "mtls", "none", "oauth2"]
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
        "allowed_cipher_suites": sorted(set(policy["allowed_cipher_suites"])),
        "minimum_key_bits": dict(policy["minimum_key_bits"]),
        "require_mutual_tls": policy["require_mutual_tls"],
        "public_route_paths": sorted(set(policy["public_route_paths"])),
    }


def normalize_inventory(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Flatten the three evidence tables without using any application code."""

    services: list[dict[str, Any]] = []
    credentials: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    for gateway in bundle["gateways"]:
        gateway_id = gateway["gateway_id"]
        for service in gateway["services"]:
            service_id = service["service_id"]
            tls = service["tls"]
            services.append(
                {
                    "gateway_id": gateway_id,
                    "service_id": service_id,
                    "cipher_suites": sorted(set(tls["cipher_suites"])),
                    "mutual_tls": tls["mutual_tls"],
                    "tls_minimum_version": tls["minimum_version"],
                }
            )
            for credential in service.get("credentials", []):
                credentials.append(
                    {
                        "gateway_id": gateway_id,
                        "service_id": service_id,
                        "credential_id": credential["credential_id"],
                        "key_type": credential["key_type"],
                        "key_bits": credential["key_bits"],
                        "secret_ref": credential["secret_ref"],
                        "inline": credential["inline"],
                    }
                )
            for route in service.get("routes", []):
                routes.append(
                    {
                        "gateway_id": gateway_id,
                        "service_id": service_id,
                        "path": route["path"],
                        "methods": sorted(set(route.get("methods", []))),
                        "authentication": route["authentication"],
                    }
                )

    services.sort(key=lambda row: (row["gateway_id"], row["service_id"]))
    credentials.sort(
        key=lambda row: (row["gateway_id"], row["service_id"], row["credential_id"])
    )
    routes.sort(key=lambda row: (row["gateway_id"], row["service_id"], row["path"]))
    return {
        "services": services,
        "credentials": credentials,
        "routes": routes,
    }


def evaluate_violations(
    bundle: dict[str, Any],
    policy: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Evaluate exactly the five specified security rules independently."""

    policy_evidence = normalized_policy(policy)
    allowed = set(policy_evidence["allowed_cipher_suites"])
    public = set(policy_evidence["public_route_paths"])
    require_mtls = policy_evidence["require_mutual_tls"]
    minimum_bits = policy_evidence["minimum_key_bits"]
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
        for cipher in service["cipher_suites"]:
            if cipher not in allowed:
                add(
                    service,
                    "CIPHER_SUITE_DEPRECATED",
                    "high",
                    cipher,
                    {
                        "allowed_cipher_suites": policy_evidence["allowed_cipher_suites"],
                        "cipher_suite": cipher,
                    },
                )
        if require_mtls and service["mutual_tls"] is False:
            add(
                service,
                "MUTUAL_TLS_NOT_ENFORCED",
                "high",
                "tls.mutual_tls",
                {"mutual_tls": False},
            )

    for credential in inventory["credentials"]:
        minimum = minimum_bits.get(credential["key_type"])
        if minimum is not None and credential["key_bits"] < minimum:
            add(
                credential,
                "WEAK_KEY_SIZE",
                "high",
                credential["credential_id"],
                {
                    "key_bits": credential["key_bits"],
                    "key_type": credential["key_type"],
                    "minimum_bits": minimum,
                },
            )
        if credential["inline"] is True:
            add(
                credential,
                "INLINE_SECRET_EXPOSED",
                "critical",
                credential["credential_id"],
                {"secret_ref": credential["secret_ref"]},
            )

    for route in inventory["routes"]:
        if route["authentication"] == "none" and route["path"] not in public:
            add(
                route,
                "ROUTE_AUTH_MISSING",
                "critical",
                route["path"],
                {"authentication": "none", "methods": route["methods"]},
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


def signature(body: bytes, secret: str = SECRET) -> str:
    """Compute the strict request signature from the exact bytes supplied."""

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def signed_request(server: Server, body: bytes) -> Response:
    """POST exact bytes with their correctly computed HMAC header."""

    return request(
        server.port,
        "POST",
        AUDIT_PATH,
        body,
        [("X-Audit-Signature", signature(body, server.secret))],
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

    allowed = sorted(set(policy["allowed_cipher_suites"]))
    assert allowed, "the shipped policy must allow at least one cipher suite"
    return {
        "service_id": service_id,
        "tls": {
            "minimum_version": "TLSv1.3",
            "mutual_tls": True,
            "cipher_suites": [allowed[0]],
        },
        "credentials": [
            {
                "credential_id": f"{service_id}-key",
                "key_type": "RSA",
                "key_bits": policy["minimum_key_bits"]["RSA"],
                "secret_ref": f"vault:{service_id}/signing",
                "inline": False,
            }
        ],
        "routes": [
            {
                "path": f"/{service_id}",
                "methods": ["GET"],
                "authentication": "oauth2",
            }
        ],
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
    allowed = sorted(set(policy["allowed_cipher_suites"]))
    minimum_bits = policy["minimum_key_bits"]
    public = sorted(set(policy["public_route_paths"]))
    bundles: list[dict[str, Any]] = []
    for bundle_index in range(14):
        gateways: list[dict[str, Any]] = []
        for gateway_index in range(bundle_index % 4):
            services: list[dict[str, Any]] = []
            service_total = (bundle_index * 3 + gateway_index) % 5
            for service_index in range(service_total):
                stem = f"b{bundle_index}-g{gateway_index}-s{service_index}"

                cipher_suites: list[str] = []
                for cipher_index in range(rng.randrange(0, 4)):
                    if rng.random() < 0.55:
                        cipher_suites.append(allowed[rng.randrange(len(allowed))])
                    else:
                        cipher_suites.append(f"WEAK-CIPHER-{rng.randrange(3)}")
                    if cipher_index == 0 and rng.random() < 0.4:
                        cipher_suites.append(cipher_suites[0])

                tls: dict[str, Any] = {
                    "minimum_version": rng.choice(TLS_VERSIONS),
                    "mutual_tls": rng.random() < 0.6,
                }
                if cipher_suites or rng.random() < 0.55:
                    tls["cipher_suites"] = cipher_suites
                else:
                    tls["cipher_suites"] = []

                credentials: list[dict[str, Any]] = []
                for key_index in range(rng.randrange(4)):
                    key_type = rng.choice(KEY_TYPES)
                    base = minimum_bits[key_type]
                    key_bits = rng.choice([max(1, base - 1), base, base + 256])
                    credentials.append(
                        {
                            "credential_id": f"{stem}-k{key_index}",
                            "key_type": key_type,
                            "key_bits": key_bits,
                            "secret_ref": f"vault:{stem}/{key_index}",
                            "inline": rng.random() < 0.35,
                        }
                    )

                route_entries: list[dict[str, Any]] = []
                for route_index in range(rng.randrange(4)):
                    if route_index == 0 and public and rng.random() < 0.3:
                        path = public[0]
                        authentication = "none"
                    else:
                        path = f"/{stem}/r{route_index}"
                        authentication = rng.choice(AUTHENTICATION_MODES)
                    methods = [
                        rng.choice(["GET", "POST", "PUT", "DELETE"])
                        for _ in range(rng.randrange(3))
                    ]
                    route_entries.append(
                        {
                            "path": path,
                            "methods": methods,
                            "authentication": authentication,
                        }
                    )

                service: dict[str, Any] = {"service_id": stem, "tls": tls}
                if credentials or rng.random() < 0.55:
                    service["credentials"] = credentials
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
# Endpoint, authentication, schema, rule, normalization, and digest tests.
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
        "CIPHER_SUITE_DEPRECATED",
        "INLINE_SECRET_EXPOSED",
        "MUTUAL_TLS_NOT_ENFORCED",
        "ROUTE_AUTH_MISSING",
        "WEAK_KEY_SIZE",
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

    wrong_raw_signature = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        pretty,
        [("X-Audit-Signature", signature(compact, audit_server.secret))],
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
    valid = signature(body, audit_server.secret)
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
        headers = [] if value is None else [("X-Audit-Signature", value)]
        response = request(audit_server.port, "POST", AUDIT_PATH, body, headers)
        assert_exact_json(response, 401, {"error": "invalid_signature"})


def test_duplicate_signature_field_lines_are_rejected(audit_server: Server) -> None:
    """Two physical X-Audit-Signature fields are invalid even when identical."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    value = signature(body, audit_server.secret)
    response = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [("X-Audit-Signature", value), ("X-Audit-Signature", value)],
    )
    assert_exact_json(response, 401, {"error": "invalid_signature"})


def test_authentication_precedes_json_parsing_and_bundle_validation(
    audit_server: Server,
) -> None:
    """Unauthenticated malformed JSON and invalid schemas must not reveal details."""

    for body in [b'{"unterminated":', b"null", b'{"bundle_id":""}']:
        response = request(
            audit_server.port,
            "POST",
            AUDIT_PATH,
            body,
            [("X-Audit-Signature", "sha256=" + "0" * 64)],
        )
        assert_exact_json(response, 401, {"error": "invalid_signature"})


def test_content_encoding_and_media_type_are_checked_after_authentication(
    audit_server: Server,
) -> None:
    """Encoding and JSON media type checks occur only after authentication."""

    body = canonical_bytes(clean_bundle(audit_server.policy))
    valid = signature(body, audit_server.secret)
    for headers, add_default in [
        ([('X-Audit-Signature', valid), ('Content-Type', 'text/plain')], True),
        ([('X-Audit-Signature', valid)], False),
    ]:
        response = request(
            audit_server.port,
            "POST",
            AUDIT_PATH,
            body,
            headers,
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

    encoded = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [("X-Audit-Signature", valid), ("Content-Encoding", "gzip")],
    )
    assert_exact_json(encoded, 415, {"error": "unsupported_content_encoding"})
    identity = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [("X-Audit-Signature", valid), ("Content-Encoding", "identity")],
    )
    assert identity.status == 200
    parameterized_json = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [
            ("X-Audit-Signature", valid),
            ("Content-Type", "Application/JSON; charset=utf-8"),
        ],
    )
    assert parameterized_json.status == 200
    unauthenticated_encoded = request(
        audit_server.port,
        "POST",
        AUDIT_PATH,
        body,
        [
            ("X-Audit-Signature", "sha256=" + "0" * 64),
            ("Content-Encoding", "gzip"),
        ],
    )
    assert_exact_json(
        unauthenticated_encoded, 401, {"error": "invalid_signature"}
    )


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

    def cred(value: Any) -> Any:
        return svc(value)["credentials"][0]

    def route(value: Any) -> Any:
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
    add("tls missing", lambda value: svc(value).pop("tls"))
    add("tls non-object", lambda value: svc(value).__setitem__("tls", []))
    add("tls version missing", lambda value: svc(value)["tls"].pop("minimum_version"))
    add("tls version invalid", lambda value: svc(value)["tls"].__setitem__("minimum_version", "TLS1.2"))
    add("mutual_tls missing", lambda value: svc(value)["tls"].pop("mutual_tls"))
    add("mutual_tls non-boolean", lambda value: svc(value)["tls"].__setitem__("mutual_tls", "true"))
    add("cipher_suites missing", lambda value: svc(value)["tls"].pop("cipher_suites"))
    add("cipher_suites non-array", lambda value: svc(value)["tls"].__setitem__("cipher_suites", {}))
    add("cipher empty", lambda value: svc(value)["tls"].__setitem__("cipher_suites", [""]))
    add("cipher non-string", lambda value: svc(value)["tls"].__setitem__("cipher_suites", [None]))
    add("cipher non-scalar", lambda value: svc(value)["tls"].__setitem__("cipher_suites", ["\udfff"]))
    add("credentials non-array", lambda value: svc(value).__setitem__("credentials", {}))
    add("credential non-object", lambda value: svc(value).__setitem__("credentials", [None]))
    add("credential id missing", lambda value: cred(value).pop("credential_id"))
    add("credential id empty", lambda value: cred(value).__setitem__("credential_id", ""))
    add("credential id non-string", lambda value: cred(value).__setitem__("credential_id", 1))
    add("key_type missing", lambda value: cred(value).pop("key_type"))
    add("key_type invalid", lambda value: cred(value).__setitem__("key_type", "DSA"))
    add("key_bits missing", lambda value: cred(value).pop("key_bits"))
    add("key_bits non-integer", lambda value: cred(value).__setitem__("key_bits", 2048.5))
    add("key_bits too small", lambda value: cred(value).__setitem__("key_bits", 0))
    add("key_bits too large", lambda value: cred(value).__setitem__("key_bits", 1_000_001))
    add("key_bits non-number", lambda value: cred(value).__setitem__("key_bits", "2048"))
    add("secret_ref missing", lambda value: cred(value).pop("secret_ref"))
    add("secret_ref empty", lambda value: cred(value).__setitem__("secret_ref", ""))
    add("secret_ref non-string", lambda value: cred(value).__setitem__("secret_ref", 5))
    add("inline missing", lambda value: cred(value).pop("inline"))
    add("inline non-boolean", lambda value: cred(value).__setitem__("inline", "true"))
    add("routes non-array", lambda value: svc(value).__setitem__("routes", {}))
    add("route non-object", lambda value: svc(value).__setitem__("routes", [None]))
    add("route path missing", lambda value: route(value).pop("path"))
    add("route path empty", lambda value: route(value).__setitem__("path", ""))
    add("route path non-string", lambda value: route(value).__setitem__("path", []))
    add("authentication missing", lambda value: route(value).pop("authentication"))
    add("authentication invalid", lambda value: route(value).__setitem__("authentication", "basic"))
    add("methods non-array", lambda value: route(value).__setitem__("methods", "GET"))
    add("method empty", lambda value: route(value).__setitem__("methods", [""]))
    add("method non-string", lambda value: route(value).__setitem__("methods", [1]))
    add("method non-scalar", lambda value: route(value).__setitem__("methods", ["\ud800"]))

    duplicate_gateway = copy.deepcopy(base["gateways"][0])
    add("duplicate gateway id", lambda value: value["gateways"].append(duplicate_gateway))
    duplicate_service = copy.deepcopy(base["gateways"][0]["services"][0])
    add("duplicate service id within gateway", lambda value: value["gateways"][0]["services"].append(duplicate_service))
    duplicate_credential = copy.deepcopy(base["gateways"][0]["services"][0]["credentials"][0])
    add("duplicate credential id within service", lambda value: svc(value)["credentials"].append(duplicate_credential))
    duplicate_route = copy.deepcopy(base["gateways"][0]["services"][0]["routes"][0])
    add("duplicate route path within service", lambda value: svc(value)["routes"].append(duplicate_route))
    return cases


def test_correctly_signed_schema_violation_matrix_is_422(audit_server: Server) -> None:
    """Every specified nested type, value, enum, and uniqueness error is 422."""

    for name, bundle in invalid_bundle_cases(audit_server.policy):
        body = (
            json.dumps(bundle, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            + "\n"
        ).encode("ascii")
        response = signed_request(audit_server, body)
        assert response.status == 422, f"{name}: {response.status} {response.body!r}"
        assert response.body == canonical_bytes({"error": "invalid_bundle"}), name


def test_uniqueness_scopes_optional_arrays_and_exact_string_deduplication(
    audit_server: Server,
) -> None:
    """Optional lists default empty while IDs may repeat only across allowed scopes."""

    policy = audit_server.policy
    allowed = sorted(set(policy["allowed_cipher_suites"]))[0]
    service_one = {
        "service_id": "shared-service-id",
        "tls": {
            "minimum_version": "TLSv1.3",
            "mutual_tls": True,
            "cipher_suites": [allowed, allowed],
        },
    }
    service_two = copy.deepcopy(service_one)
    service_two["tls"]["cipher_suites"] = []
    service_three = copy.deepcopy(service_one)
    service_three["service_id"] = "different-service-same-child-identifiers"
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


def test_all_five_rules_obey_strict_cutoffs_public_paths_and_key_bounds(
    audit_server: Server,
) -> None:
    """Boundary cases for every rule must yield exactly the expected records."""

    policy = audit_server.policy
    allowed = sorted(set(policy["allowed_cipher_suites"]))[0]
    weak_cipher = "TLS_RSA_WITH_RC4_128_SHA"
    assert weak_cipher not in policy["allowed_cipher_suites"]
    public_path = sorted(set(policy["public_route_paths"]))[0]
    min_rsa = policy["minimum_key_bits"]["RSA"]
    min_ec = policy["minimum_key_bits"]["EC"]
    matrix = {
        "service_id": "rule-matrix",
        "tls": {
            "minimum_version": "TLSv1.2",
            "mutual_tls": False,
            "cipher_suites": [weak_cipher, allowed],
        },
        "credentials": [
            {"credential_id": "weak", "key_type": "RSA", "key_bits": min_rsa - 1, "secret_ref": "vault:a", "inline": False},
            {"credential_id": "exact", "key_type": "RSA", "key_bits": min_rsa, "secret_ref": "vault:b", "inline": False},
            {"credential_id": "inline", "key_type": "EC", "key_bits": min_ec, "secret_ref": "vault:c", "inline": True},
        ],
        "routes": [
            {"path": "/private", "methods": ["GET"], "authentication": "none"},
            {"path": public_path, "methods": ["GET"], "authentication": "none"},
            {"path": "/ok", "methods": ["POST"], "authentication": "oauth2"},
        ],
    }
    bundle = {
        "bundle_id": "all-rule-boundaries",
        "audit_at": "2026-06-15T00:00:00.000Z",
        "gateways": [{"gateway_id": "gw-rules", "services": [matrix]}],
    }
    _, expected = assert_success(audit_server, bundle)
    violations = expected["violations"]

    matrix_pairs = [(item["code"], item["subject"]) for item in violations]
    assert matrix_pairs == [
        ("CIPHER_SUITE_DEPRECATED", weak_cipher),
        ("INLINE_SECRET_EXPOSED", "inline"),
        ("MUTUAL_TLS_NOT_ENFORCED", "tls.mutual_tls"),
        ("ROUTE_AUTH_MISSING", "/private"),
        ("WEAK_KEY_SIZE", "weak"),
    ]
    weak = next(item for item in violations if item["code"] == "WEAK_KEY_SIZE")
    assert weak["evidence"] == {
        "key_bits": min_rsa - 1,
        "key_type": "RSA",
        "minimum_bits": min_rsa,
    }
    route_missing = next(
        item for item in violations if item["code"] == "ROUTE_AUTH_MISSING"
    )
    assert route_missing["evidence"] == {"authentication": "none", "methods": ["GET"]}


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
                    "tls": {
                        "minimum_version": "TLSv1.3",
                        "mutual_tls": False,
                        "cipher_suites": [],
                    },
                    "credentials": [],
                    "routes": [],
                }
            ],
        }
    ]
    _, expected = assert_success(audit_server, empty_children)
    assert expected["service_count"] == 1
    assert [row["code"] for row in expected["violations"]] == [
        "MUTUAL_TLS_NOT_ENFORCED"
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


def test_permutation_whitespace_key_order_and_set_duplicates_are_invariant(
    audit_server: Server,
) -> None:
    """Every declared non-semantic ordering and dedup change preserves response bytes."""

    policy = audit_server.policy
    allowed = sorted(set(policy["allowed_cipher_suites"]))
    min_ec = policy["minimum_key_bits"]["EC"]
    services: list[dict[str, Any]] = []
    for index in range(4):
        service = clean_service(policy, f"permuted-{index}")
        first_cipher = service["tls"]["cipher_suites"][0]
        service["tls"]["cipher_suites"] = [first_cipher, allowed[-1], first_cipher]
        service["credentials"].append(
            {
                "credential_id": f"permuted-{index}-key-b",
                "key_type": "EC",
                "key_bits": min_ec,
                "secret_ref": f"vault:permuted-{index}/b",
                "inline": False,
            }
        )
        service["routes"][0]["methods"] = ["GET", "POST", "GET"]
        service["routes"].append(
            {
                "path": f"/permuted-{index}/b",
                "methods": ["DELETE", "DELETE"],
                "authentication": "oauth2",
            }
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
            service["tls"]["ignored_tls_field"] = [1, 2, 3]
            service["credentials"].reverse()
            service["routes"].reverse()
            service["tls"]["cipher_suites"] = sorted(
                set(service["tls"]["cipher_suites"]), reverse=True
            )
            for route in service["routes"]:
                route["methods"] = sorted(set(route["methods"]), reverse=True)

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
    changed["gateways"][0]["services"][0]["credentials"][0][
        "secret_ref"
    ] = "vault:rotated/signing"
    _, first = assert_success(audit_server, original)
    _, second = assert_success(audit_server, changed)
    assert first["violations"] == second["violations"] == []
    assert first["evidence_digest"] != second["evidence_digest"]


def test_custom_runtime_policy_drives_health_rules_and_digest(
    tmp_path: Path,
) -> None:
    """A selected policy file, including allowlist dedup, must replace defaults."""

    custom_policy = {
        "public_route_paths": ["/status", "/status"],
        "require_mutual_tls": False,
        "minimum_key_bits": {"RSA": 4096, "EC": 384, "Ed25519": 256},
        "allowed_cipher_suites": ["TLS_AES_256_GCM_SHA384", "TLS_AES_256_GCM_SHA384"],
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
            "tls": {
                "minimum_version": "TLSv1.2",
                "mutual_tls": False,
                "cipher_suites": ["TLS_AES_128_GCM_SHA256"],
            },
            "credentials": [
                {
                    "credential_id": "custom-key",
                    "key_type": "RSA",
                    "key_bits": 2048,
                    "secret_ref": "vault:custom",
                    "inline": False,
                }
            ],
            "routes": [
                {"path": "/private", "methods": ["GET"], "authentication": "none"},
                {"path": "/status", "methods": ["GET"], "authentication": "none"},
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
            ("CIPHER_SUITE_DEPRECATED", "TLS_AES_128_GCM_SHA256"),
            ("ROUTE_AUTH_MISSING", "/private"),
            ("WEAK_KEY_SIZE", "custom-key"),
        ]
    finally:
        server.stop()


def test_recursive_utf8_canonical_bytes_and_digest_preimage(audit_server: Server) -> None:
    """Non-ASCII evidence must remain UTF-8 and hash the exact newline-terminated preimage."""

    policy = audit_server.policy
    bundle = clean_bundle(policy)
    bundle["bundle_id"] = "release-雪-π"
    bundle["gateways"][0]["gateway_id"] = "网关"
    service = bundle["gateways"][0]["services"][0]
    service["service_id"] = "serviço"
    service["tls"]["cipher_suites"].extend(["不安全", "", "\U00010000"])
    raw = json.dumps(bundle, ensure_ascii=True, indent=1).encode("ascii")
    response, expected = assert_success(audit_server, bundle, raw)
    payload, expected_bytes, preimage = oracle_result(bundle, policy)
    assert response.body == expected_bytes
    assert "release-雪-π".encode("utf-8") in response.body
    assert b"release-\\u96ea" not in response.body
    assert preimage.endswith(b"\n") and not preimage.endswith(b"\n\n")
    assert expected["evidence_digest"] == hashlib.sha256(preimage).hexdigest()
    assert payload["evidence_digest"] == expected["evidence_digest"]
    subjects = [
        row["subject"]
        for row in expected["violations"]
        if row["code"] == "CIPHER_SUITE_DEPRECATED"
    ]
    assert subjects == sorted(["不安全", "", "\U00010000"])


# ---------------------------------------------------------------------------
# Startup and tool/security-specific implementation requirements.
# ---------------------------------------------------------------------------


def test_startup_requires_a_nonempty_utf8_hmac_secret() -> None:
    """Both unset and empty AUDIT_HMAC_SECRET must fail fast with the required message."""

    for secret_value in [None, ""]:
        environment = os.environ.copy()
        environment["SECURITY_POLICY_PATH"] = str(POLICY_PATH)
        if secret_value is None:
            environment.pop("AUDIT_HMAC_SECRET", None)
        else:
            environment["AUDIT_HMAC_SECRET"] = secret_value
        returncode, output, stayed_alive = run_startup_probe(environment)
        assert not stayed_alive, "server remained alive without a usable secret"
        assert returncode != 0
        assert "AUDIT_HMAC_SECRET is required" in output


def test_startup_fails_when_selected_policy_cannot_be_loaded_or_validated(
    tmp_path: Path,
) -> None:
    """Missing, malformed, and structurally invalid policy files must be fatal."""

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"policy_version":"only-one-field"}', encoding="utf-8")
    oversized_bits = tmp_path / "oversized-bits.json"
    oversized_bits.write_bytes(
        canonical_bytes(
            {
                "policy_version": "invalid-bits",
                "allowed_cipher_suites": ["TLS_AES_128_GCM_SHA256"],
                "minimum_key_bits": {"EC": 256, "Ed25519": 256, "RSA": 1_000_001},
                "require_mutual_tls": True,
                "public_route_paths": ["/status"],
            }
        )
    )
    missing_key_type = tmp_path / "missing-key-type.json"
    missing_key_type.write_bytes(
        canonical_bytes(
            {
                "policy_version": "missing-ed25519",
                "allowed_cipher_suites": ["TLS_AES_128_GCM_SHA256"],
                "minimum_key_bits": {"EC": 256, "RSA": 2048},
                "require_mutual_tls": True,
                "public_route_paths": ["/status"],
            }
        )
    )
    bad_boolean = tmp_path / "bad-boolean.json"
    bad_boolean.write_bytes(
        canonical_bytes(
            {
                "policy_version": "bad-boolean",
                "allowed_cipher_suites": ["TLS_AES_128_GCM_SHA256"],
                "minimum_key_bits": {"EC": 256, "Ed25519": 256, "RSA": 2048},
                "require_mutual_tls": "yes",
                "public_route_paths": ["/status"],
            }
        )
    )
    non_scalar = tmp_path / "non-scalar-policy.json"
    non_scalar.write_text(
        '{"allowed_cipher_suites":["\\ud800"],"minimum_key_bits":{"EC":256,'
        '"Ed25519":256,"RSA":2048},"public_route_paths":["/status"],'
        '"require_mutual_tls":true,"policy_version":"invalid"}\n',
        encoding="ascii",
    )
    for path in [
        tmp_path / "does-not-exist.json",
        malformed,
        invalid,
        oversized_bits,
        missing_key_type,
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
        "services, credentials, and routes each require a Polars explode"
    )
    assert re.search(r"\btimingSafeEqual\s*\(", active_source), (
        "well-formed HMAC bytes must be compared with crypto.timingSafeEqual"
    )
