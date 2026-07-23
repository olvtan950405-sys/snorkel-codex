"""Black-box and source-integrity checks for the MLflow request leak firewall."""

import json
import os
import secrets
import subprocess
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
BIN = APP / "bin/mlflow-gateway"


@pytest.fixture(scope="session", autouse=True)
def build_gateway():
    """Build the executable from the submitted Go source before behavioral checks."""
    subprocess.run(["go", "build", "-o", str(BIN), "./cmd/mlflow-gateway"], cwd=APP, check=True)


def invoke(tmp_path, records=None, raw=None, old_output=None):
    inp, out = tmp_path / "requests.jsonl", tmp_path / "safe.jsonl"
    if raw is None:
        raw = "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in records)
    inp.write_text(raw)
    if old_output is not None:
        out.write_text(old_output)
    proc = subprocess.run(
        [str(BIN), "scrub", "--input", str(inp), "--output", str(out)],
        text=True, capture_output=True,
    )
    parsed = [json.loads(x) for x in out.read_text().splitlines()] if proc.returncode == 0 else None
    return proc, out, parsed


def base(path="/api/2.0/mlflow/runs/create", method="POST"):
    return {"id": secrets.token_hex(6), "method": method, "path": path}


def test_all_exact_routes_and_methods(tmp_path):
    """Classify every supported endpoint exactly, normalize method/path, and reject near misses."""
    specs = [
        ("POST", "/api/2.0/mlflow/runs/create/", "create_run"),
        ("post", "/api/2.0/mlflow/runs/log-batch", "log_batch"),
        ("POST", "/api/2.0/mlflow/runs/set-tag", "set_tag"),
        ("get", "/api/2.0/mlflow/runs/get", "get_run"),
        ("GET", "/api/2.0/mlflow/artifacts/get-download-uri", "artifact_uri"),
    ]
    records = [base(p, m) for m, p, _ in specs]
    records += [base("/api/2.0/mlflow/runs/get", "POST"), base("/x/api/2.0/mlflow/runs/create", "POST")]
    proc, _, got = invoke(tmp_path, records)
    assert proc.returncode == 0, proc.stderr
    assert [x["route"] for x in got[:5]] == [x[2] for x in specs]
    assert [x["request"]["method"] for x in got[:5]] == [x[0].upper() for x in specs]
    assert got[0]["request"]["path"].endswith("/create")
    assert [x["reason"] for x in got[5:]] == ["method_not_allowed", "unsupported_endpoint"]


def test_headers_query_and_nested_mlflow_tags_are_scrubbed(tmp_path):
    """Redact randomized credentials recursively while retaining ordinary telemetry values."""
    vals = ["Bearer " + secrets.token_urlsafe(25), secrets.token_hex(24), secrets.token_urlsafe(28)]
    r = base()
    r.update({
        "headers": {"Authorization": vals[0], "X-API-Key": vals[1], "Accept": "application/json"},
        "query": {"X-Amz-Security-Token": vals[2], "page": "4"},
        "body": {"password": vals[0], "nested": [{"CLIENT_SECRET": {"raw": vals[1]}},
                 {"key": "mlflow.user", "value": vals[2]},
                 {"key": "team", "value": "forecasting"}]},
    })
    proc, out, got = invoke(tmp_path, [r])
    assert proc.returncode == 0, proc.stderr
    text = out.read_text()
    assert all(v not in text for v in vals)
    req = got[0]["request"]
    assert req["headers"] == {"Accept": "application/json", "Authorization": "[REDACTED]", "X-API-Key": "[REDACTED]"}
    assert req["query"] == {"X-Amz-Security-Token": "[REDACTED]", "page": "4"}
    assert req["body"]["nested"][1]["value"] == "[REDACTED]"
    assert req["body"]["nested"][2]["value"] == "forecasting"


def test_presigned_urls_are_canonical_and_safe_schemes_enforced(tmp_path):
    """Scrub signed HTTP URLs canonically and reject userinfo, remote file URLs, and alien schemes."""
    sig = secrets.token_hex(30)
    good = base(); good["body"] = {"artifact_uri": f"https://store.test/z?part=2&X-Amz-Signature={sig}&a=1"}
    bad = []
    for uri in ["https://user:pass@store.test/a", "file://remote/etc/passwd", "ftp://store.test/a"]:
        r = base(); r["body"] = {"artifact_uri": uri}; bad.append(r)
    proc, out, got = invoke(tmp_path, [good] + bad)
    assert proc.returncode == 0, proc.stderr
    assert sig not in out.read_text()
    assert got[0]["request"]["body"]["artifact_uri"] == "https://store.test/z?X-Amz-Signature=%5BREDACTED%5D&a=1&part=2"
    assert [x["reason"] for x in got[1:]] == ["unsafe_artifact_uri"] * 3


def test_rejections_disclose_no_request_material_and_follow_precedence(tmp_path):
    """Rejected records use the minimal schema and endpoint policy wins over secret scanning."""
    secret = secrets.token_urlsafe(32)
    unknown = base("/api/1.0/mlflow/runs/create"); unknown["headers"] = {"Authorization": secret}
    query_path = base("/api/2.0/mlflow/runs/create?token=" + secret)
    proc, out, got = invoke(tmp_path, [unknown, query_path])
    assert proc.returncode == 0, proc.stderr
    assert secret not in out.read_text()
    assert got == [
        {"id": unknown["id"], "decision": "reject", "reason": "unsupported_endpoint"},
        {"id": query_path["id"], "decision": "reject", "reason": "credential_in_path"},
    ]


@pytest.mark.parametrize("raw", [
    '{"id":"x","id":"y","method":"GET","path":"/api/2.0/mlflow/runs/get"}\n',
    '{"id":"x","method":"GET","path":"/api/2.0/mlflow/runs/get","body":{"a":1,"a":2}}\n',
    '{"id":"x","method":"GET","path":"/api/2.0/mlflow/runs/get","extra":1}\n',
    '{"id":"x","method":"GET","path":"/api/2.0/mlflow/runs/get","headers":{"x":3}}\n',
    '{broken\n',
])
def test_malformed_stream_is_atomic(tmp_path, raw):
    """Duplicate keys, schema violations, and invalid JSON fail without replacing prior output."""
    proc, out, _ = invoke(tmp_path, raw=raw, old_output="KEEP\n")
    assert proc.returncode != 0
    assert out.read_text() == "KEEP\n"


def test_absent_values_and_json_types_survive(tmp_path):
    """Emit required empty maps/null and preserve nonsensitive booleans, numbers, arrays, and Unicode."""
    a = base("/api/2.0/mlflow/runs/get", "GET")
    b = base(); b["body"] = {"metric": 1.25, "ok": True, "none": None, "names": ["λ", 7]}
    proc, _, got = invoke(tmp_path, [a, b])
    assert proc.returncode == 0, proc.stderr
    assert got[0]["request"] == {"method": "GET", "path": "/api/2.0/mlflow/runs/get", "headers": {}, "query": {}, "body": None}
    assert got[1]["request"]["body"] == b["body"]


def test_output_is_byte_deterministic_and_source_is_go_parseable(tmp_path):
    """Repeated runs are byte-identical and every submitted Go source parses as valid Go AST."""
    r = base(); r["headers"] = {"z": "9", "a": "1"}; r["body"] = {"z": 1, "a": 2}
    first_dir, second_dir = tmp_path / "a", tmp_path / "b"; first_dir.mkdir(); second_dir.mkdir()
    p1, o1, _ = invoke(first_dir, [r]); p2, o2, _ = invoke(second_dir, [r])
    assert p1.returncode == p2.returncode == 0
    assert o1.read_bytes() == o2.read_bytes()
    check = tmp_path / "parse.go"
    check.write_text('package main\nimport("go/parser";"go/token";"os";"path/filepath")\nfunc main(){filepath.Walk(os.Args[1],func(p string,i os.FileInfo,e error)error{if e==nil&&filepath.Ext(p)==".go"{if _,x:=parser.ParseFile(token.NewFileSet(),p,nil,parser.AllErrors);x!=nil{panic(x)}};return e})}\n')
    subprocess.run(["go", "run", str(check), str(APP)], check=True, cwd=APP)


def test_incident_capture_is_fully_sanitized(tmp_path):
    """The supplied incident fixture processes end to end without any known credential leakage."""
    out = tmp_path / "capture-safe.jsonl"
    proc = subprocess.run([str(BIN), "scrub", "--input", str(APP / "fixtures/incident-requests.jsonl"), "--output", str(out)], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    text = out.read_text()
    for fragment in ["incident-bearer-81ac", "incident-key-441", "incident-query-token", "operator@example.test", "cafebabe"]:
        assert fragment not in text
    rows = [json.loads(x) for x in text.splitlines()]
    assert [x["decision"] for x in rows] == ["forward", "forward", "reject"]
