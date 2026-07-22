import base64, csv, hashlib, hmac, json, os, secrets, socket, sqlite3, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
BIN = APP / "bin/refundguard"

@pytest.fixture(scope="session", autouse=True)
def build():
    subprocess.run(["npm", "run", "build"], cwd=APP, check=True)
    BIN.write_bytes((APP / "dist/cli.js").read_bytes()); BIN.chmod(0o755)

def b64(x): return base64.urlsafe_b64encode(x).rstrip(b"=").decode()
def token(payload, key, alg="HS256"):
    head = b64(json.dumps({"typ":"JWT", "alg":alg}, separators=(",", ":")).encode())
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = b64(hmac.new(key.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()) if alg == "HS256" else ""
    return f"{head}.{body}.{sig}"

def free_port():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p

def request(port, tok):
    import urllib.request, urllib.error
    r=urllib.request.Request(f"http://127.0.0.1:{port}/refunds", data=b"{}", method="POST", headers={"Content-Type":"application/json","Authorization":"Bearer "+tok})
    try:
        with urllib.request.urlopen(r) as z: return z.status, json.load(z)
    except urllib.error.HTTPError as e: return e.code, json.load(e)

def test_server_enforces_signature_algorithm_and_claims(tmp_path):
    port=free_port(); key=secrets.token_urlsafe(24)
    env=os.environ|{"PORT":str(port),"REFUND_JWT_KEY":key}
    proc=subprocess.Popen([str(BIN),"serve"],cwd=APP,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1",port),.1).close(); break
            except OSError: time.sleep(.05)
        now=int(time.time()); good={"sub":"u1","merchant":"m1","scope":"read refund:write","iat":now-2,"exp":now+60,"iss":"payments-api","aud":["refunds"]}
        assert request(port,token(good,key))[0] == 202
        assert request(port,token(good,"wrong"))[0] == 401
        assert request(port,token(good,key,"none"))[0] == 401
        for field in ["sub","merchant","scope","iat","exp","iss","aud"]:
            bad=good.copy(); bad.pop(field); assert request(port,token(bad,key))[0] == 401
        expired=good|{"exp":now-1}; assert request(port,token(expired,key))[0] == 401
    finally: proc.terminate(); proc.wait(timeout=5)

class OSV(BaseHTTPRequestHandler):
    calls=[]
    def do_POST(self):
        n=int(self.headers["content-length"]); q=json.loads(self.rfile.read(n)); self.__class__.calls.append(q)
        name=q["package"]["name"]
        data={"vulns":[{"id":"OSV-Z","summary":"z issue"},{"id":"OSV-A"}]} if name=="alpha" else {"vulns":[]}
        raw=json.dumps(data).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*args): pass

@pytest.fixture
def osv():
    OSV.calls=[]; server=ThreadingHTTPServer(("127.0.0.1",0),OSV); t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
    yield f"http://127.0.0.1:{server.server_port}/query",OSV.calls
    server.shutdown()

def write_inputs(p):
    ledger=p/"refunds.csv"
    rows=[["event_id","created_at","merchant","amount_cents","token_kid","token_alg","token_signature"],
      ["e1","2026-01-01T00:00:00Z","Zulu","10","shared","HS256","same"],
      ["e2","2026-01-01T00:01:00Z","Alpha","20","shared","HS256","same"],
      ["e3","2026-01-01T00:02:00Z","Alpha","30","old","NONE","x"]]
    with ledger.open("w",newline="") as f: csv.writer(f).writerows(rows)
    lock=p/"package-lock.json"; lock.write_text(json.dumps({"name":"alpha","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"root","version":"9"},"node_modules/b":{"name":"beta","version":"2"},"node_modules/a":{"name":"alpha","version":"1"},"node_modules/dup":{"name":"alpha","version":"1"}}}))
    return ledger,lock

def run_analysis(p,url):
    ledger,lock=write_inputs(p); db=p/"out.sqlite"; report=p/"report.json"
    r=subprocess.run([str(BIN),"analyze","--ledger",str(ledger),"--lockfile",str(lock),"--database",str(db),"--report",str(report)],env=os.environ|{"OSV_API_URL":url},text=True,capture_output=True)
    return r,db,report

def test_analysis_sqlite_report_osv_and_determinism(tmp_path,osv):
    r,db,report=run_analysis(tmp_path,osv[0]); assert r.returncode==0,r.stderr
    with sqlite3.connect(db) as c:
        assert c.execute("select count(*) from refund_events").fetchone()==(3,)
        assert c.execute("select typeof(amount_cents) from refund_events limit 1").fetchone()==("integer",)
    got=json.loads(report.read_text()); assert got["ledger_rows"]==3
    assert got["suspicious"]==[
      {"token_kid":"old","token_alg":"none","token_signature":"x","event_count":1,"merchants":["Alpha"]},
      {"token_kid":"shared","token_alg":"hs256","token_signature":"same","event_count":2,"merchants":["Alpha","Zulu"]}]
    assert got["vulnerabilities"]==[
      {"id":"OSV-A","package":"alpha","version":"1","summary":""},
      {"id":"OSV-Z","package":"alpha","version":"1","summary":"z issue"}]
    assert [(x["package"]["name"],x["version"]) for x in osv[1]]==[("alpha","1"),("beta","2"),("root","9")]
    before=report.read_bytes(); r,_,_=run_analysis(tmp_path,osv[0]); assert r.returncode==0 and report.read_bytes()==before

@pytest.mark.parametrize("mutation",["bad_header","duplicate","bad_amount","bad_date"])
def test_invalid_ledgers_do_not_replace_outputs(tmp_path,osv,mutation):
    ledger,lock=write_inputs(tmp_path); rows=list(csv.reader(ledger.open()))
    if mutation=="bad_header": rows[0][-1]="signature"
    elif mutation=="duplicate": rows.append(rows[1])
    elif mutation=="bad_amount": rows[1][3]="1.5"
    else: rows[1][1]="yesterday"
    with ledger.open("w",newline="") as f: csv.writer(f).writerows(rows)
    db=tmp_path/"out.sqlite"; report=tmp_path/"report.json"; db.write_bytes(b"KEEPDB"); report.write_text("KEEPREPORT")
    r=subprocess.run([str(BIN),"analyze","--ledger",str(ledger),"--lockfile",str(lock),"--database",str(db),"--report",str(report)],env=os.environ|{"OSV_API_URL":osv[0]},capture_output=True)
    assert r.returncode!=0 and db.read_bytes()==b"KEEPDB" and report.read_text()=="KEEPREPORT"

def test_osv_failure_is_atomic(tmp_path):
    ledger,lock=write_inputs(tmp_path); db=tmp_path/"x.db"; rep=tmp_path/"x.json"; db.write_bytes(b"D"); rep.write_bytes(b"R")
    r=subprocess.run([str(BIN),"analyze","--ledger",str(ledger),"--lockfile",str(lock),"--database",str(db),"--report",str(rep)],env=os.environ|{"OSV_API_URL":"http://127.0.0.1:1/query"},capture_output=True)
    assert r.returncode!=0 and db.read_bytes()==b"D" and rep.read_bytes()==b"R"
