import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";
import {parse} from "csv-parse/sync";

const HEAD = ["event_id","created_at","merchant","amount_cents","token_kid","token_alg","token_signature"];
type Row = Record<string,string>;

function validDate(s:string): boolean {
  return /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(s) && !Number.isNaN(Date.parse(s));
}
function temporary(target:string): string {
  return path.join(path.dirname(path.resolve(target)), `.${path.basename(target)}.${process.pid}.${Date.now()}.tmp`);
}

export async function analyze(ledger:string, lockfile:string, database:string, report:string):Promise<void> {
  const records = parse(fs.readFileSync(ledger,"utf8"), {columns:false, bom:true, relax_column_count:false, skip_empty_lines:false}) as string[][];
  if (!records.length || records[0].length!==HEAD.length || records[0].some((v,i)=>v!==HEAD[i])) throw new Error("invalid CSV header");
  const seen=new Set<string>(); const rows:Row[]=[];
  for (const values of records.slice(1)) {
    if (values.length!==HEAD.length) throw new Error("invalid CSV row");
    const r=Object.fromEntries(HEAD.map((h,i)=>[h,values[i]]));
    if (!r.event_id || seen.has(r.event_id) || !validDate(r.created_at) || !r.merchant ||
        !/^[1-9]\d*$/.test(r.amount_cents) || !Number.isSafeInteger(Number(r.amount_cents)) ||
        !r.token_kid || !r.token_alg || !r.token_signature) throw new Error("invalid ledger value");
    seen.add(r.event_id); rows.push(r);
  }
  const lock=JSON.parse(fs.readFileSync(lockfile,"utf8"));
  if (![2,3].includes(lock.lockfileVersion) || !lock.packages || typeof lock.packages!=="object") throw new Error("invalid lockfile");
  const packages=new Map<string,{name:string,version:string}>();
  const candidates=[{name:lock.name,version:lock.version},...Object.values(lock.packages)] as any[];
  for (const p of candidates) if (p && typeof p.name==="string" && p.name && typeof p.version==="string" && p.version) packages.set(`${p.name}\0${p.version}`,{name:p.name,version:p.version});
  const ordered=[...packages.values()].sort((a,b)=>a.name.localeCompare(b.name)||a.version.localeCompare(b.version));
  const vulns:any[]=[]; const endpoint=process.env.OSV_API_URL || "https://api.osv.dev/v1/query";
  for (const p of ordered) {
    const response=await fetch(endpoint,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({package:{ecosystem:"npm",name:p.name},version:p.version}),signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error(`OSV returned ${response.status}`);
    const body:any=await response.json(); if (!body || (body.vulns!==undefined && !Array.isArray(body.vulns))) throw new Error("invalid OSV response");
    for (const v of body.vulns||[]) if (v && typeof v.id==="string" && v.id) vulns.push({id:v.id,package:p.name,version:p.version,summary:typeof v.summary==="string"?v.summary:""});
  }
  const dbtmp=temporary(database), reptmp=temporary(report); let db:Database.Database|undefined;
  try {
    db=new Database(dbtmp);
    db.exec("CREATE TABLE refund_events(event_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, merchant TEXT NOT NULL, amount_cents INTEGER NOT NULL, token_kid TEXT NOT NULL, token_alg TEXT NOT NULL, token_signature TEXT NOT NULL)");
    const ins=db.prepare("INSERT INTO refund_events VALUES(?,?,?,?,?,?,?)");
    db.transaction(()=>rows.forEach(r=>ins.run(r.event_id,r.created_at,r.merchant,Number(r.amount_cents),r.token_kid,r.token_alg,r.token_signature)))();
    const groups=db.prepare(`SELECT token_kid, lower(token_alg) token_alg, token_signature, count(*) event_count, group_concat(merchant, char(31)) merchants FROM (SELECT DISTINCT token_kid, token_alg, token_signature, event_id, merchant FROM refund_events ORDER BY merchant) GROUP BY token_kid, lower(token_alg), token_signature HAVING count(DISTINCT merchant)>1 OR lower(token_alg)='none' ORDER BY token_kid, lower(token_alg), token_signature`).all() as any[];
    const suspicious=groups.map(g=>({token_kid:g.token_kid,token_alg:g.token_alg,token_signature:g.token_signature,event_count:g.event_count,merchants:[...new Set(String(g.merchants).split("\x1f"))].sort()}));
    const unique=new Map<string,any>(); for(const v of vulns) unique.set(`${v.id}\0${v.package}\0${v.version}`,v);
    const vulnerabilities=[...unique.values()].sort((a,b)=>a.id.localeCompare(b.id)||a.package.localeCompare(b.package)||a.version.localeCompare(b.version));
    db.close(); db=undefined;
    fs.writeFileSync(reptmp,JSON.stringify({ledger_rows:rows.length,suspicious,vulnerabilities},null,2)+"\n");
    fs.renameSync(dbtmp,database); fs.renameSync(reptmp,report);
  } catch(e) { if(db) db.close(); for(const f of [dbtmp,reptmp]) try{fs.unlinkSync(f)}catch{} throw e; }
}
