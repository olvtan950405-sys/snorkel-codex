import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
BIN = APP / "bin/mlflow-audit"
SEED = "17" * 32

@pytest.fixture(scope="session", autouse=True)
def build():
    subprocess.run(["go", "build", "-o", str(BIN), "./cmd/mlflow-audit"], cwd=APP, check=True)

def call(tmp_path, rows=None, raw=None, seed=SEED, old=None):
    src, dst = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    src.write_text(raw if raw is not None else "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
    if old is not None: dst.write_text(old)
    p = subprocess.run([str(BIN), "sanitize", "--input", str(src), "--output", str(dst), "--seed", seed], text=True, capture_output=True)
    parsed = [json.loads(x) for x in dst.read_text().splitlines()] if p.returncode == 0 else None
    return p, dst, parsed

def req(seq, method="POST", path="/api/2.0/mlflow/runs/log-metric"):
    return {"seq": seq, "method": method, "path": path}

def base_bytes(row):
    row = dict(row); row.pop("chain")
    return json.dumps(row, separators=(",", ":"), ensure_ascii=False, sort_keys=False).encode()

def test_routes_normalization_and_precedence(tmp_path):
    specs=[("post","/api/2.0/mlflow/runs/log-metric/","log_metric"),("POST","/api/2.0/mlflow/runs/log-parameter","log_parameter"),("POST","/api/2.0/mlflow/runs/set-tag","set_tag"),("get","/api/2.0/mlflow/runs/get","get_run"),("delete","/api/2.0/mlflow/runs/delete","delete_run")]
    rows=[req(i+1,m,p) for i,(m,p,_) in enumerate(specs)]
    rows += [req(7,"POST","/api/2.0/mlflow/runs/get"), req(8,"GET","/api/1.0/mlflow/runs/get"), req(9,"GET","/api/2.0/mlflow/runs/get?token=x")]
    p,_,got=call(tmp_path,rows); assert p.returncode==0,p.stderr
    assert [r["route"] for r in got[:5]]==[x[2] for x in specs]
    assert [r["reason"] for r in got[5:]]==["method_not_allowed","unsupported_endpoint","query_in_path"]
    assert got[0]["request"]["path"].endswith("log-metric") and got[0]["request"]["method"]=="POST"

def test_random_secrets_and_tags_are_removed(tmp_path):
    vals=[secrets.token_urlsafe(25) for _ in range(5)]
    r=req(2);r["headers"]={"Authorization":vals[0],"X-API-Key":vals[1],"Accept":"json"};r["body"]={"password":vals[2],"nested":[{"CLIENT_SECRET":vals[3]},{"key":"mlflow.user","value":vals[4]},{"key":"team","value":"risk"}]}
    p,out,got=call(tmp_path,[r]);assert p.returncode==0,p.stderr
    assert all(v not in out.read_text() for v in vals)
    assert got[0]["request"]["headers"]["Accept"]=="json"
    assert got[0]["request"]["body"]["nested"][2]["value"]=="risk"

def test_url_canonicalization_and_unsafe_rejections(tmp_path):
    sig=secrets.token_hex(24); good=req(1);good["body"]={"uri":f"https://s.test/a?z=2&X-Amz-Signature={sig}&a=1"}
    rows=[good]
    for i,u in enumerate(["ftp://s.test/a","https://u:p@s.test/a","file://remote/etc/x"],2):r=req(i);r["body"]={"uri":u};rows.append(r)
    p,out,got=call(tmp_path,rows);assert p.returncode==0,p.stderr;assert sig not in out.read_text()
    assert got[0]["request"]["body"]["uri"]=="https://s.test/a?X-Amz-Signature=%5BREDACTED%5D&a=1&z=2"
    assert [r["reason"] for r in got[1:]]==["unsafe_uri"]*3
    assert all(set(r)=={"seq","decision","reason","chain"} for r in got[1:])

def test_chain_is_exact_and_tamper_evident(tmp_path):
    p,_,got=call(tmp_path,[req(3),req(8,"GET","/unknown")]);assert p.returncode==0
    prev=bytes.fromhex(SEED)
    for row in got:
        expected=hashlib.sha256(prev+base_bytes(row)).hexdigest()
        assert row["chain"]==expected
        prev=bytes.fromhex(expected)
    altered=req(3);altered["body"]={"metric":99}
    other_dir = tmp_path / "other"; other_dir.mkdir()
    _,_,other=call(other_dir,[altered,req(8,"GET","/unknown")])
    assert got[0]["chain"]!=other[0]["chain"] and got[1]["chain"]!=other[1]["chain"]

@pytest.mark.parametrize("raw",[
    '{"seq":1,"seq":2,"method":"GET","path":"/api/2.0/mlflow/runs/get"}\n',
    '{"seq":1,"method":"GET","path":"/api/2.0/mlflow/runs/get","body":{"x":1,"x":2}}\n',
    '{"seq":1.0,"method":"GET","path":"/api/2.0/mlflow/runs/get"}\n',
    '{"seq":1,"method":"GET","path":"/api/2.0/mlflow/runs/get","extra":true}\n',
    '{bad\n',
])
def test_malformed_is_atomic(tmp_path,raw):
    p,out,_=call(tmp_path,raw=raw,old="KEEP\n");assert p.returncode!=0;assert out.read_text()=="KEEP\n"

def test_sequence_and_seed_validation_are_atomic(tmp_path):
    for n,(rows,seed) in enumerate([([req(2),req(2)],SEED),([req(3),req(2)],SEED),([req(1)],"AB"*32),([req(1)],"0"*63)]):
        d=tmp_path/str(n);d.mkdir();p,out,_=call(d,rows,seed=seed,old="OLD\n");assert p.returncode!=0;assert out.read_text()=="OLD\n"

def test_fixture_determinism_defaults_and_no_demo_leaks(tmp_path):
    rows=[json.loads(x) for x in (APP/"fixtures/capture.jsonl").read_text().splitlines()]
    a=tmp_path/"a";b=tmp_path/"b";a.mkdir();b.mkdir();p1,o1,g=call(a,rows);p2,o2,_=call(b,rows)
    assert p1.returncode==p2.returncode==0 and o1.read_bytes()==o2.read_bytes()
    assert g[0]["request"]["headers"]["Accept"]=="application/json" and g[1]["request"]["body"]["value"]=="[REDACTED]"
    assert g[2]["reason"]=="query_in_path"
    assert not any(x in o1.read_text() for x in ["demo-chain-secret","demo-signature","analyst@example.test","demo-query"])
