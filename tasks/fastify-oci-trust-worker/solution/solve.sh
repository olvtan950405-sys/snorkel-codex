#!/usr/bin/env bash
set -euo pipefail

cat > /app/src/verifier.js <<'JS'
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const ORDER = ['TAG_NOT_ANNOTATED','TAG_SIGNATURE_INVALID','TAG_KEY_UNAUTHORIZED','TAG_COMMIT_MISMATCH','TAG_DIGEST_TRAILER_INVALID','ARTIFACT_MISSING','ARTIFACT_SIZE_MISMATCH','ARTIFACT_DIGEST_MISMATCH','OCI_DOCUMENT_INVALID','OCI_IDENTITY_MISMATCH','HOOK_MISSING','HOOK_MODE_INVALID','HOOK_DIGEST_MISMATCH'];
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const IMAGE = /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$/;
const HEX40 = /^[0-9a-f]{40}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const scalar = x => typeof x === 'string' && x.length > 0 && !/[\uD800-\uDFFF]/u.test(x);
const exact = (x, keys) => x && typeof x === 'object' && !Array.isArray(x) && Object.keys(x).sort().join('\0') === [...keys].sort().join('\0');
const bytesort = (a,b) => Buffer.from(a).compare(Buffer.from(b));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
function sortObject(x) { if (Array.isArray(x)) return x.map(sortObject); if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort(bytesort).map(k => [k,sortObject(x[k])])); return x; }
const canonical = x => Buffer.from(JSON.stringify(sortObject(x)) + '\n');
function regular(p) { const s=fs.lstatSync(p); if (!s.isFile() || s.isSymbolicLink()) throw new Error('unsafe input'); return p; }
function readJson(p) { return JSON.parse(fs.readFileSync(regular(p),'utf8')); }
function safeRepoPath(p) { return scalar(p) && p.startsWith('.githooks/') && !p.split('/').some(x=>!x||x==='.'||x==='..') && !p.startsWith('/'); }
function git(remote,args,env={}) { return spawnSync('git',['-c','protocol.file.allow=always','-c','core.hooksPath=/dev/null','--git-dir',remote,...args],{encoding:'utf8',env:{PATH:process.env.PATH,HOME:'/nonexistent',GIT_CONFIG_NOSYSTEM:'1',GIT_TERMINAL_PROMPT:'0',...env}}); }
function blob(remote,commit,name) { const q=git(remote,['ls-tree','-z',commit,'--',name]); if(q.status!==0) return null; const line=q.stdout.split('\0')[0]; if(!line) return null; const m=/^(\d{6}) blob ([0-9a-f]{40})\t(.+)$/.exec(line); if(!m||m[3]!==name) return null; const c=git(remote,['cat-file','blob',m[2]],{}); return c.status===0 ? {mode:m[1],bytes:Buffer.from(c.stdout)} : null; }
function validate(req,rows,policy,keyring) {
  if(!exact(req,['image','tag','platform','remote','corpus','policy','keyring'])||!IMAGE.test(req.image)||!SAFE_ID.test(req.tag)||!['linux/amd64','linux/arm64'].includes(req.platform)) throw Error('request');
  for(const k of ['remote','corpus','policy','keyring']) if(!path.isAbsolute(req[k])) throw Error('path');
  if(!fs.lstatSync(req.remote).isDirectory()||fs.lstatSync(req.remote).isSymbolicLink()||!fs.lstatSync(req.corpus).isDirectory()||fs.lstatSync(req.corpus).isSymbolicLink()) throw Error('path');
  if(!Array.isArray(rows)) throw Error('rows'); let prior=''; const seen=new Set();
  for(const r of rows) { if(!exact(r,['image','tag','platform','commit','artifact','artifact_sha256','artifact_size'])||!IMAGE.test(r.image)||!SAFE_ID.test(r.tag)||!['linux/amd64','linux/arm64'].includes(r.platform)||!HEX40.test(r.commit)||!HEX64.test(r.artifact_sha256)||!Number.isInteger(r.artifact_size)||r.artifact_size<0||r.artifact_size>1e9||!scalar(r.artifact)||r.artifact.startsWith('/')||r.artifact.split('/').some(x=>!x||x==='.'||x==='..')) throw Error('row'); const id=[r.image,r.tag,r.platform].join('\0'); if(seen.has(id)||bytesort(prior,id)>0) throw Error('order'); seen.add(id); prior=id; }
  if(!exact(policy,['policy_version','allowed_release_keys','required_hooks'])||!scalar(policy.policy_version)||!Array.isArray(policy.allowed_release_keys)||!exact(policy.required_hooks,Object.keys(policy.required_hooks))) throw Error('policy');
  if(new Set(policy.allowed_release_keys).size!==policy.allowed_release_keys.length||policy.allowed_release_keys.some(x=>!SAFE_ID.test(x))||[...policy.allowed_release_keys].sort(bytesort).join()!==policy.allowed_release_keys.join()) throw Error('policy');
  const hooks=Object.keys(policy.required_hooks); if(!hooks.length||[...hooks].sort(bytesort).join()!==hooks.join()||hooks.some(x=>!safeRepoPath(x)||!HEX64.test(policy.required_hooks[x]))) throw Error('hooks');
  if(!exact(keyring,['keys'])||!Array.isArray(keyring.keys)) throw Error('keys'); prior=''; seen.clear(); for(const k of keyring.keys){if(!exact(k,['key_id','public_key'])||!SAFE_ID.test(k.key_id)||!scalar(k.public_key)||seen.has(k.key_id)||bytesort(prior,k.key_id)>0)throw Error('key');seen.add(k.key_id);prior=k.key_id;}
}
function oci(bytes,req) { try { const x=JSON.parse(bytes.toString('utf8')); if(!canonical(x).equals(bytes)||!exact(x,['schemaVersion','mediaType','name','platform','config','layers'])||x.schemaVersion!==2||x.mediaType!=='application/vnd.oci.image.manifest.v1+json'||!exact(x.config,['digest'])||!/^sha256:[0-9a-f]{64}$/.test(x.config.digest)||!Array.isArray(x.layers)||!x.layers.length) return ['OCI_DOCUMENT_INVALID']; const ds=[]; for(const l of x.layers){if(!exact(l,['digest','size'])||!/^sha256:[0-9a-f]{64}$/.test(l.digest)||!Number.isInteger(l.size)||l.size<0)return ['OCI_DOCUMENT_INVALID'];ds.push(l.digest)} if(new Set(ds).size!==ds.length)return ['OCI_DOCUMENT_INVALID']; return x.name===req.image&&x.platform===req.platform?[]:['OCI_IDENTITY_MISMATCH']; } catch{return ['OCI_DOCUMENT_INVALID'];} }
function q(s){return `"${String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n')}"`;}
function graph(req,policy,reasons){const bad=reasons.length>0; const nodes=[['request',`${req.image}:${req.tag}`,'box'],['tag',req.tag,'oval'],['commit','commit','box'],['artifact','OCI manifest','note'],...Object.keys(policy.required_hooks).map(h=>[`hook:${h}`,h,'component'])];let lines=['digraph oci_trust {','  graph [rankdir="LR"]'];for(const [id,label,shape] of nodes)lines.push(`  ${q(id)} [id=${q(id)}, label=${q(label)}, shape=${q(shape)}, status=${q(bad?'rejected':'trusted')}]`);lines.push('  "request" -> "tag"','  "tag" -> "commit"','  "commit" -> "artifact"');for(const h of Object.keys(policy.required_hooks))lines.push(`  "commit" -> ${q(`hook:${h}`)}`);return lines.join('\n')+'\n}\n';}
export function evaluate(req,out){
  const rows=readJson(path.join(req.corpus,'records.json')), policy=readJson(req.policy), keyring=readJson(req.keyring); validate(req,rows,policy,keyring); const row=rows.find(r=>r.image===req.image&&r.tag===req.tag&&r.platform===req.platform); if(!row)throw Error('record');
  const found=[]; let signer=null, commit=null, artifact=null; const ref=`refs/tags/${req.tag}`; const typ=git(req.remote,['cat-file','-t',ref]); if(typ.status!==0||typ.stdout.trim()!=='tag')found.push('TAG_NOT_ANNOTATED');
  if(!found.includes('TAG_NOT_ANNOTATED')) { const peeled=git(req.remote,['rev-parse','--verify',`${ref}^{commit}`]); if(peeled.status===0)commit=peeled.stdout.trim(); const raw=git(req.remote,['cat-file','tag',ref]); const trailers=(raw.stdout.match(/^OCI-Artifact-SHA256: ([0-9a-f]{64})$/gm)||[]); if(trailers.length!==1||trailers[0]!==`OCI-Artifact-SHA256: ${row.artifact_sha256}`)found.push('TAG_DIGEST_TRAILER_INVALID');
    const home=fs.mkdtempSync(path.join(os.tmpdir(),'trust-gnupg-')); fs.chmodSync(home,0o700); try { const fps=new Map(); for(const k of keyring.keys){const before=new Set(spawnSync('gpg',['--homedir',home,'--batch','--with-colons','--fingerprint'],{encoding:'utf8'}).stdout.split('\n').filter(x=>x.startsWith('fpr:')).map(x=>x.split(':')[9]));const imp=spawnSync('gpg',['--homedir',home,'--batch','--import'],{input:k.public_key,encoding:'utf8'});if(imp.status!==0)throw Error('key import');const after=spawnSync('gpg',['--homedir',home,'--batch','--with-colons','--fingerprint'],{encoding:'utf8'}).stdout.split('\n').filter(x=>x.startsWith('fpr:')).map(x=>x.split(':')[9]);for(const f of after)if(!before.has(f))fps.set(f,k.key_id)} const v=git(req.remote,['verify-tag','--raw',ref],{GNUPGHOME:home});const m=/\[GNUPG:\] VALIDSIG ([0-9A-F]+)/.exec(v.stderr);if(v.status!==0||!m)found.push('TAG_SIGNATURE_INVALID');else if(!fps.has(m[1])||!policy.allowed_release_keys.includes(fps.get(m[1])))found.push('TAG_KEY_UNAUTHORIZED');else signer=fps.get(m[1]); } finally {fs.rmSync(home,{recursive:true,force:true});}
  }
  if(commit!==row.commit)found.push('TAG_COMMIT_MISMATCH');
  if(commit){artifact=blob(req.remote,commit,row.artifact);if(!artifact)found.push('ARTIFACT_MISSING');else{if(artifact.bytes.length!==row.artifact_size)found.push('ARTIFACT_SIZE_MISMATCH');if(sha(artifact.bytes)!==row.artifact_sha256)found.push('ARTIFACT_DIGEST_MISMATCH');found.push(...oci(artifact.bytes,req));}for(const h of Object.keys(policy.required_hooks)){const b=blob(req.remote,commit,h);if(!b)found.push('HOOK_MISSING');else{if(b.mode!=='100755')found.push('HOOK_MODE_INVALID');if(sha(b.bytes)!==policy.required_hooks[h])found.push('HOOK_DIGEST_MISMATCH');}}}
  const reasons=ORDER.filter(x=>found.includes(x)); const base={artifact_sha256:artifact?sha(artifact.bytes):null,commit,evidence_sha256:null,image:req.image,platform:req.platform,policy_version:policy.policy_version,reasons,signer,status:reasons.length?'rejected':'accepted',tag:req.tag};base.evidence_sha256=sha(canonical(Object.fromEntries(Object.entries(base).filter(([k])=>k!=='evidence_sha256'))));const dot=graph(req,policy,reasons);const tmp=fs.mkdtempSync(path.join(path.dirname(out),'trust-out-'));try{fs.writeFileSync(path.join(tmp,'decision.json'),canonical(base));fs.writeFileSync(path.join(tmp,'trust.dot'),dot);const plain=spawnSync('dot',['-Tplain',path.join(tmp,'trust.dot')]);if(plain.status!==0)throw Error('dot');fs.writeFileSync(path.join(tmp,'trust.plain'),plain.stdout);fs.rmSync(out,{recursive:true,force:true});fs.renameSync(tmp,out);}catch(e){fs.rmSync(tmp,{recursive:true,force:true});throw e;}return base;
}
JS

chmod +x /app/bin/trust-worker.js
