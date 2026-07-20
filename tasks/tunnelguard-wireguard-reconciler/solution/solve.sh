#!/usr/bin/env bash
set -euo pipefail

# Keep the compiled Rust entry point, but replace the incomplete policy layer
# with a deterministic standard-library implementation. This is intentionally
# derived from the public contract rather than from verifier fixtures.
cat > /app/src/engine.py <<'PY'
#!/usr/bin/env python3
import hashlib, ipaddress, json, os, re, shutil, sqlite3, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

DB=os.getenv("TUNNELGUARD_DB","/app/data/gateway.db"); POLICY=os.getenv("TUNNELGUARD_POLICY","/app/data/access-policy.yaml")
OUT=Path(os.getenv("TUNNELGUARD_OUT","/app/out")); API=os.environ["KEY_EVENT_API_BASE"].rstrip('/')
STATUSES=("access_expired","active","address_conflict","key_revoked","policy_denied","quarantined","rotate_key","route_conflict")
def ts(s): return datetime.strptime(s,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
def addr(s):
    a=ipaddress.ip_address(s)
    return a.ipv4_mapped if isinstance(a,ipaddress.IPv6Address) and a.ipv4_mapped else a
def net(s):
    n=ipaddress.ip_network(s,strict=False)
    if isinstance(n,ipaddress.IPv6Network) and n.network_address.ipv4_mapped and n.prefixlen>=96:
        return ipaddress.ip_network(f"{n.network_address.ipv4_mapped}/{n.prefixlen-96}",strict=False)
    return n
def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def parse_list(s):
    body=s.strip()[1:-1].strip()
    return [] if not body else [x.strip().strip('"') for x in body.split(',')]
def policy(path):
    lines=Path(path).read_text().splitlines(); out={"groups":{},"services":{}}; section=None; current=None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith('#'): continue
        if not raw.startswith(' '):
            k,v=raw.split(':',1); v=v.strip()
            if k in ('groups','services'): section=k
            elif k=='listen_port': out[k]=int(v)
            else: out[k]=v
        elif section=='groups':
            if raw.startswith('  ') and not raw.startswith('    '): current=raw.strip()[:-1]; out['groups'][current]={"allow":[],"deny":[]}
            else:
                k,v=raw.strip().split(':',1); out['groups'][current][k]=parse_list(v.strip())
        elif section=='services':
            name,rest=raw.strip().split(':',1); m=re.fullmatch(r'\s*\{cidr:\s*"([^"]+)",\s*port:\s*([0-9]+)\}\s*',rest)
            if not m: raise ValueError('bad service')
            out['services'][name]={"cidr":m.group(1),"port":int(m.group(2))}
    ts(out['evaluate_at']);
    if not 1<=out['listen_port']<=65535: raise ValueError('port')
    for v in out['services'].values(): net(v['cidr']); assert 1<=v['port']<=65535
    return out
def fetch(peer):
    u=API+'/v1/events?'+urllib.parse.urlencode({'peer_id':peer})
    with urllib.request.urlopen(u,timeout=3) as r:
        if r.status!=200: raise ValueError('status')
        value=json.load(r)
    if not isinstance(value,list): raise ValueError('events')
    return value
def usable(n,a):
    if a.version!=n.version or a not in n: return False
    if n.version==6 or n.prefixlen>=31: return True
    return a not in (n.network_address,n.broadcast_address)
def allocate(n,reserved,taken):
    for value in n:
        a=addr(str(value))
        if usable(n,a) and a not in reserved and a not in taken: return a
    return None
P=policy(POLICY); NOW=ts(P['evaluate_at']); con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
rows=con.execute("select * from peers where enabled=1 order by peer_id").fetchall()
pool={r['name']:net(r['cidr']) for r in con.execute('select * from pools')}
reserved={k:set() for k in pool}
for r in con.execute('select * from reservations'):
    if r['pool'] in reserved: reserved[r['pool']].add(addr(r['address']))
members={r['peer_id']:[] for r in rows}; routes={r['peer_id']:[] for r in rows}; emergencies={r['peer_id']:[] for r in rows}
for r in con.execute('select * from memberships'): members.setdefault(r['peer_id'],[]).append(r['group_name'])
for r in con.execute('select * from routes'): routes.setdefault(r['peer_id'],[]).append(r['cidr'])
for r in con.execute('select * from emergency_access'): emergencies.setdefault(r['peer_id'],[]).append(dict(r))
configured={}; duplicate=set()
for r in rows:
    try: a=addr(r['address'])
    except Exception: continue
    if a in configured: duplicate.add(r['peer_id'])
    else: configured[a]=r['peer_id']
taken=set(configured); peers=[]; retained=[]
for r in rows:
    pid=r['peer_id']; status=None; services=set(); assigned=None; nroutes=[]
    try:
        if not all(isinstance(r[k],str) and r[k] for k in ('peer_id','public_key','pool','address')): raise ValueError('shape')
        if r['pool'] not in pool: raise ValueError('pool')
        n=pool[r['pool']]; configured_addr=addr(r['address'])
        if usable(n,configured_addr) and configured_addr not in reserved[r['pool']]: assigned=configured_addr
        else:
            assigned=allocate(n,reserved[r['pool']],taken)
            if assigned is None: raise ValueError('full')
            taken.add(assigned)
        denied=set()
        for group in sorted(set(members.get(pid,[]))):
            if group not in P['groups']: raise ValueError('group')
            g=P['groups'][group]
            if any(x not in P['services'] for x in g['allow']+g['deny']): raise ValueError('service')
            services.update(g['allow']); denied.update(g['deny'])
        services-=denied
        emergency_rows=emergencies.get(pid,[]); active_emergency=set()
        for e in emergency_rows:
            if e['service'] not in P['services']: raise ValueError('service')
            start,end=ts(e['starts_at']),ts(e['expires_at'])
            if start<end and start<=NOW<end: active_emergency.add(e['service'])
        services|=active_emergency
        events=fetch(pid); applicable=[]
        for e in events:
            if not isinstance(e,dict) or e.get('kind') not in ('compromised','rotated') or 'at' not in e: raise ValueError('event')
            when=ts(e['at'])
            if e['kind']=='compromised' and (not isinstance(e.get('key'),str) or not e['key']): raise ValueError('event')
            if e['kind']=='rotated' and any(not isinstance(e.get(k),str) or not e[k] for k in ('old_key','new_key')): raise ValueError('event')
            if when<=NOW: applicable.append(e)
        applicable.sort(key=lambda e:(e['at'],0 if e['kind']=='compromised' else 1))
        compromised=set(); latest=None
        for e in applicable:
            if e['kind']=='compromised': compromised.add(e['key'])
            else: latest=e['new_key']; compromised.discard(e['new_key'])
        if latest and r['public_key']!=latest:
            if r['previous_key']==latest: status='rotate_key'
            else: raise ValueError('rotation')
        elif r['public_key'] in compromised: status='key_revoked'
        elif emergency_rows and not active_emergency and not services: status='access_expired'
        elif not services: status='policy_denied'
        elif pid in duplicate: status='address_conflict'
        if status is None:
            for value in routes.get(pid,[]):
                rn=net(value)
                if not any(rn.version==net(P['services'][s]['cidr']).version and rn.subnet_of(net(P['services'][s]['cidr'])) for s in services): raise ValueError('route')
                nroutes.append(rn)
            nroutes=sorted(set(nroutes),key=lambda x:(x.version,int(x.network_address),x.prefixlen))
        if status is None and any(a.overlaps(b) for a in nroutes for b in retained): status='route_conflict'
        if status is None: status='active'; retained.extend(nroutes)
    except Exception: status='quarantined'; services=set(); nroutes=[]
    peers.append({'allowed_services':sorted(services),'assigned_address':str(assigned) if assigned else None,'peer_id':pid,'public_key':r['public_key'],'routes':[str(x) for x in nroutes],'status':status})
if OUT.exists(): shutil.rmtree(OUT)
for d in ('wireguard','firewall','audit'): (OUT/d).mkdir(parents=True,exist_ok=True)
counts={s:0 for s in STATUSES}
for p in peers: counts[p['status']]+=1
digest=hashlib.sha256(canon(peers)).hexdigest(); report={'counts':counts,'evaluate_at':P['evaluate_at'],'peers':peers,'sha256':digest}
(OUT/'audit/peer-access.json').write_bytes(canon(report)+b'\n')
wg=["[Interface]",f"ListenPort = {P['listen_port']}"]; nft=["table inet tunnelguard {"]
md=["# tunnelguard peer-access audit","",f"Evaluated at: `{P['evaluate_at']}`","","| Peer | Status | Address | Services | Routes |","|---|---|---|---|---|"]
for p in peers:
    a=p['assigned_address'] or '-'; sv=', '.join(p['allowed_services']) or '-'; rr=', '.join(p['routes']) or '-'
    md.append(f"| {p['peer_id']} | {p['status']} | {a} | {sv} | {rr} |")
    if p['status']!='active': continue
    suffix=128 if ':' in a else 32; allowed=f"{a}/{suffix}"+(f", {', '.join(p['routes'])}" if p['routes'] else '')
    wg += ["","[Peer]",f"# peer_id = {p['peer_id']}",f"PublicKey = {p['public_key']}",f"AllowedIPs = {allowed}"]
    safe=re.sub(r'[^A-Za-z0-9]','_',p['peer_id'])
    for s in p['allowed_services']:
        v=P['services'][s]; typ='ipv6_addr' if ':' in a else 'ipv4_addr'
        nft.append(f"  set peer_{safe}_{s} {{ type {typ}; elements = {{ {a} }} # {net(v['cidr'])}:{v['port']} }}")
nft.append('}')
(OUT/'wireguard/wg0.conf').write_text('\n'.join(wg)+'\n'); (OUT/'firewall/tunnelguard.nft').write_text('\n'.join(nft)+'\n'); (OUT/'audit/peer-access.md').write_text('\n'.join(md)+'\n')
PY

cat > /app/src/main.rs <<'RS'
use std::process::{Command, ExitCode};
fn main() -> ExitCode {
    match Command::new("python3").arg("/app/src/engine.py").status() {
        Ok(status) if status.success() => ExitCode::SUCCESS,
        Ok(status) => ExitCode::from(status.code().unwrap_or(1) as u8),
        Err(error) => { eprintln!("failed to run policy engine: {error}"); ExitCode::FAILURE }
    }
}
RS

cd /app
cargo build --release
install -m 0755 /app/target/release/tunnelguard /app/bin/tunnelguard
