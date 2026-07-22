#!/usr/bin/env bash
set -euo pipefail
cd /app

cat > /app/bin/export-guard.ts <<'TS'
#!/usr/bin/env node
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { DuckDBInstance } from "@duckdb/node-api";

const execute = promisify(execFile);
const reasons = new Set<string>();
const safePath = (s: unknown) => typeof s === "string" && s.length > 0 && !s.startsWith("/") && !s.endsWith("/") && !s.includes("//") && s.split("/").every(x => x !== "." && x !== ".." && /^[A-Za-z0-9._-]+$/.test(x));
const exactKeys = (v: any, keys: string[]) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join() === [...keys].sort().join();
const output = (value: any, code: number) => { console.log(JSON.stringify(value, Object.keys(value).sort())); process.exitCode = code; };
const reject = () => output({reasons:[...reasons].sort(),status:"rejected"}, 1);
async function git(args: string[], options: any = {}) { return (await execute("git", args, {encoding:"utf8", maxBuffer:4*1024*1024, ...options})).stdout; }

async function main() {
  const at = process.argv.indexOf("--export");
  if (at < 0 || at + 1 >= process.argv.length) { reasons.add("INVALID_EXPORT"); return reject(); }
  let exp: any, cfg: any;
  try {
    exp=JSON.parse(await readFile(process.argv[at+1],"utf8"));
    cfg=JSON.parse(await readFile(process.env.EXPORT_GUARD_CONFIG || "/app/config/worker.json","utf8"));
  } catch { reasons.add("INVALID_EXPORT"); return reject(); }
  const ids=new Set(), paths=new Set();
  if (!exactKeys(exp,["dashboardId","requestedBy","charts"]) || !Number.isSafeInteger(exp.dashboardId) || exp.dashboardId<1 || typeof exp.requestedBy!=="string" || !exp.requestedBy || !Array.isArray(exp.charts) || !exp.charts.length) reasons.add("INVALID_EXPORT");
  else for (const c of exp.charts) {
    if (!exactKeys(c,["id","thumbnail","oid","size"]) || !Number.isSafeInteger(c.id) || c.id<1 || !safePath(c.thumbnail) || !/^[0-9a-f]{64}$/.test(c.oid) || !Number.isSafeInteger(c.size) || c.size<0 || ids.has(c.id) || paths.has(c.thumbnail)) reasons.add("INVALID_EXPORT");
    ids.add(c.id); paths.add(c.thumbnail);
  }
  if (reasons.size) return reject();
  const remote=process.env.POLICY_REMOTE || cfg.policyRemote, db=process.env.AUDIT_DB || cfg.auditDatabase, source=process.env.SOURCE_REPO || "/app";
  if (typeof cfg.policyRef!=="string" || !/^refs\/tags\/v\d+\.\d+\.\d+$/.test(cfg.policyRef)) { reasons.add("POLICY_REF_INVALID"); return reject(); }
  if (typeof remote!=="string" || !remote || !/^[0-9a-f]{40}$/.test(cfg.policyCommit) || !safePath(cfg.policySubmodule)) { reasons.add("POLICY_PIN_MISMATCH"); return reject(); }
  let resolved="";
  try {
    const lines=(await git(["ls-remote","--tags","--",remote,cfg.policyRef,cfg.policyRef+"^{}"])).trim().split("\n").filter(Boolean);
    const peeled=lines.find(x=>x.endsWith("^{}")); const direct=lines.find(x=>!x.endsWith("^{}")); resolved=(peeled||direct||"").split(/\s+/)[0]||"";
    const tree=(await git(["-C",source,"ls-tree","HEAD","--",cfg.policySubmodule])).trim().split(/\s+/);
    if (resolved!==cfg.policyCommit || tree[0]!=="160000" || tree[2]!==cfg.policyCommit) reasons.add("POLICY_PIN_MISMATCH");
  } catch { reasons.add("POLICY_PIN_MISMATCH"); }
  if (reasons.size) return reject();
  try {
    const instance=await DuckDBInstance.create(db); const connection=await instance.connect();
    const reader=await connection.runAndReadAll("SELECT decision FROM export_audit WHERE dashboard_id=$1 AND actor=$2 ORDER BY occurred_at DESC LIMIT 1",[exp.dashboardId,exp.requestedBy]);
    const row=reader.getRowObjectsJS()[0]; connection.closeSync();
    if (!row || row.decision!=="allow") reasons.add("AUDIT_DENIED");
  } catch { reasons.add("AUDIT_DENIED"); }
  if (reasons.size) return reject();
  const temp=await mkdtemp(join(tmpdir(),"export-guard-"));
  try {
    const env={...process.env,GIT_LFS_SKIP_SMUDGE:"1",GIT_ALLOW_PROTOCOL:"file"};
    await git(["clone","-q","--no-checkout","--",remote,temp],{env}); await git(["-C",temp,"checkout","-q","--detach",resolved],{env});
    let policy:any;
    try { policy=JSON.parse(await git(["-C",temp,"show",resolved+":policy.json"])); } catch { reasons.add("POLICY_INVALID"); return reject(); }
    const allowed=policy && policy.version===1 && exactKeys(policy,["version","dashboards"]) && policy.dashboards && policy.dashboards[String(exp.dashboardId)];
    if (!Array.isArray(allowed) || allowed.some((x:any,i:number)=>!Number.isSafeInteger(x) || x<1 || (i && x<=allowed[i-1]))) reasons.add("POLICY_INVALID");
    else for (const c of exp.charts) if (!allowed.includes(c.id)) reasons.add("CHART_NOT_ALLOWED");
    if (reasons.size) return reject();
    for (const c of exp.charts) {
      let pointer=""; try { pointer=await git(["-C",temp,"show",resolved+":"+c.thumbnail]); } catch {}
      const match=/^version https:\/\/git-lfs\.github\.com\/spec\/v1\noid sha256:([0-9a-f]{64})\nsize (0|[1-9][0-9]*)\n$/.exec(pointer);
      if (!match || match[1]!==c.oid || Number(match[2])!==c.size) reasons.add("LFS_POINTER_INVALID");
    }
    if (reasons.size) return reject();
    try { await git(["-C",temp,"lfs","pull","origin"],{env}); } catch { reasons.add("THUMBNAIL_MISMATCH"); return reject(); }
    for (const c of exp.charts) {
      try { const bytes=await readFile(join(temp,...c.thumbnail.split("/"))); if (bytes.length!==c.size || createHash("sha256").update(bytes).digest("hex")!==c.oid) reasons.add("THUMBNAIL_MISMATCH"); }
      catch { reasons.add("THUMBNAIL_MISMATCH"); }
    }
  } finally { await rm(temp,{recursive:true,force:true}); }
  if (reasons.size) return reject();
  output({charts:exp.charts.length,dashboardId:exp.dashboardId,policyCommit:resolved,status:"approved"},0);
}
main().catch(()=>{ reasons.add("POLICY_INVALID"); reject(); });
TS
chmod +x /app/bin/export-guard.ts

commit=$(git --git-dir=/srv/policy-remotes/export-policy.git rev-parse refs/tags/v1.0.0^\{commit\})
node -e 'const fs=require("fs"); const p="/app/config/worker.json"; const c=JSON.parse(fs.readFileSync(p)); c.policyRef="refs/tags/v1.0.0"; c.policyCommit=process.argv[1]; fs.writeFileSync(p,JSON.stringify(c,null,2)+"\n")' "$commit"
