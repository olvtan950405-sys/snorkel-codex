import json, os, subprocess, time
from pathlib import Path

APP=Path("/app")
BIN=APP/"bin/locksmith-audit"
API=APP/"bin/locksmith-api"
KEY="0123456789abcdef0123456789abcdef"

def invoke(tmp_path, requests=None, modules=None, report=None, key=KEY):
    req=tmp_path/"requests.json"; req.write_text(json.dumps(requests if requests is not None else [
        {"method":"POST","path":"/leases","body":{"ID":"z-lease","Subject":"zoe","TTL":600}},
        {"method":"POST","path":"/rotate","body":{}},
        {"method":"POST","path":"/leases","body":{"ID":"a-lease","Subject":"amy","TTL":1200}}]))
    mod=tmp_path/"modules.json"; mod.write_text(json.dumps(modules if modules is not None else {"modules":[]}))
    out=report or tmp_path/"report.json"
    p=subprocess.run([str(BIN),"--api",str(API),"--requests",str(req),"--modules",str(mod),"--master-key",key,"--report",str(out)],text=True,capture_output=True,timeout=30)
    return p,out

def test_runtime_rotation_bbolt_reconciliation_and_canonical_report(tmp_path):
    p,out=invoke(tmp_path); assert p.returncode==0,p.stderr
    raw=out.read_text(); got=json.loads(raw)
    assert list(got)==["tokens","leases","modules"] and raw.endswith("\n")
    assert [x["lease_id"] for x in got["tokens"]]==["a-lease","z-lease"]
    assert [x["kid"] for x in got["tokens"]]==["k2","k1"]
    assert [(x["id"],x["subject"],x["kid"]) for x in got["leases"]]==[("a-lease","amy","k2"),("z-lease","zoe","k1")]
    assert all(t["exp"]>t["iat"] for t in got["tokens"])
    assert [x["expires_at"] for x in got["leases"]]==[x["exp"] for x in got["tokens"]]
    assert got["modules"]==[]
    time.sleep(.1)
    assert subprocess.run(["pgrep","-f",f"^{API}$"],capture_output=True).returncode!=0

def test_invalid_key_does_not_replace_evidence(tmp_path):
    out=tmp_path/"report.json"; out.write_bytes(b"KEEP\n")
    p,_=invoke(tmp_path,report=out,key="short")
    assert p.returncode!=0 and out.read_bytes()==b"KEEP\n"

def test_unknown_request_fields_are_rejected_atomically(tmp_path):
    out=tmp_path/"report.json"; out.write_bytes(b"ORIGINAL")
    requests=[{"method":"POST","path":"/leases","body":{},"extra":True}]
    p,_=invoke(tmp_path,requests=requests,report=out)
    assert p.returncode!=0 and out.read_bytes()==b"ORIGINAL"

def test_mutable_or_malformed_module_policy_is_rejected(tmp_path):
    out=tmp_path/"report.json"; out.write_bytes(b"OLD")
    policy={"modules":[{"module":"example.invalid/m","version":"v1.2.3","tag":"main","remote":"/tmp/no.git"}]}
    p,_=invoke(tmp_path,modules=policy,report=out)
    assert p.returncode!=0 and out.read_bytes()==b"OLD"
