"""Behavioral checks for OCI provenance, signed tags, hooks, and graph snapshots."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

import pytest

APP = pathlib.Path('/app')

def run(*args, cwd=None, env=None, input=None, check=True):
    """Run an isolated fixture command."""
    return subprocess.run(args, cwd=cwd, env=env, input=input, text=True, capture_output=True, check=check)

def canon(value):
    """Return contract canonical JSON bytes."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()

@pytest.fixture()
def incident(tmp_path):
    """Create evidence not present in the shipped corpus."""
    home = tmp_path/'gnupg'; home.mkdir(mode=0o700)
    env = dict(os.environ, GNUPGHOME=str(home))
    run('gpg','--batch','--passphrase','','--quick-generate-key','Release Fixture <release@example.invalid>','rsa2048','sign','1d',env=env)
    listing=run('gpg','--batch','--with-colons','--list-secret-keys',env=env).stdout
    fingerprint=next(x.split(':')[9] for x in listing.splitlines() if x.startswith('fpr:'))
    public=run('gpg','--batch','--armor','--export',fingerprint,env=env).stdout
    work=tmp_path/'work'; remote=tmp_path/'remote.git'; work.mkdir()
    run('git','init','-q',cwd=work); run('git','config','user.name','Fixture',cwd=work); run('git','config','user.email','fixture@example.invalid',cwd=work)
    hook=b'#!/bin/sh\nexit 0\n'; (work/'.githooks').mkdir(); (work/'.githooks/pre-receive').write_bytes(hook); os.chmod(work/'.githooks/pre-receive',0o755)
    manifest={'config':{'digest':'sha256:'+'1'*64},'layers':[{'digest':'sha256:'+'2'*64,'size':7}],'mediaType':'application/vnd.oci.image.manifest.v1+json','name':'registry.example/team/widget','platform':'linux/amd64','schemaVersion':2}
    artifact=canon(manifest); (work/'release.oci.json').write_bytes(artifact)
    run('git','add','.githooks/pre-receive','release.oci.json',cwd=work); run('git','commit','-qm','fixture',cwd=work)
    commit=run('git','rev-parse','HEAD',cwd=work).stdout.strip(); digest=hashlib.sha256(artifact).hexdigest()
    run('git','tag','-s','-u',fingerprint,'-m',f'release\n\nOCI-Artifact-SHA256: {digest}','v2.7.1',cwd=work,env=env)
    run('git','init','--bare','-q',str(remote)); run('git','push','-q',str(remote),'HEAD:refs/heads/main','refs/tags/v2.7.1',cwd=work)
    corpus=tmp_path/'corpus'; corpus.mkdir(); records=[{'artifact':'release.oci.json','artifact_sha256':digest,'artifact_size':len(artifact),'commit':commit,'image':manifest['name'],'platform':manifest['platform'],'tag':'v2.7.1'}]; (corpus/'records.json').write_bytes(canon(records))
    policy={'allowed_release_keys':['release-prod'],'policy_version':'2026-07','required_hooks':{'.githooks/pre-receive':hashlib.sha256(hook).hexdigest()}}
    keyring={'keys':[{'key_id':'release-prod','public_key':public}]}
    (tmp_path/'policy.json').write_bytes(canon(policy)); (tmp_path/'keys.json').write_bytes(canon(keyring))
    request={'corpus':str(corpus),'image':manifest['name'],'keyring':str(tmp_path/'keys.json'),'platform':manifest['platform'],'policy':str(tmp_path/'policy.json'),'remote':str(remote),'tag':'v2.7.1'}
    (tmp_path/'request.json').write_bytes(canon(request))
    return tmp_path, request, records[0]

def invoke(root, request):
    """Invoke the public CLI and load its artifacts."""
    (root/'request.json').write_bytes(canon(request)); out=root/'out'
    result=run('node',str(APP/'bin/trust-worker.js'),'verify','--request',str(root/'request.json'),'--out',str(out),check=False)
    return result, out

def test_accepts_signed_bound_release_and_snapshots_graph(incident):
    """A fully bound signed tag emits canonical JSON and dot's exact plain output."""
    root, request, record=incident; result,out=invoke(root,request)
    assert result.returncode == 0 and result.stdout == ''
    decision=json.loads((out/'decision.json').read_text()); assert decision['status']=='accepted' and decision['commit']==record['commit'] and decision['signer']=='release-prod'
    assert (out/'decision.json').read_bytes()==canon(decision)
    expected=run('dot','-Tplain',str(out/'trust.dot')).stdout.encode(); assert (out/'trust.plain').read_bytes()==expected

def test_lightweight_or_moved_tag_is_rejected(incident):
    """Replacing the annotated release tag with a lightweight tag cannot retain trust."""
    root,request,_=incident; run('git','--git-dir',request['remote'],'tag','-f','v2.7.1','refs/heads/main')
    result,out=invoke(root,request); assert result.returncode==0
    decision=json.loads((out/'decision.json').read_text()); assert decision['status']=='rejected' and 'TAG_NOT_ANNOTATED' in decision['reasons']

def test_hook_policy_is_bound_to_committed_mode_and_bytes(incident):
    """A different required hook digest rejects while preserving reason precedence."""
    root,request,_=incident; policy=json.loads(pathlib.Path(request['policy']).read_text()); policy['required_hooks']['.githooks/pre-receive']='0'*64; pathlib.Path(request['policy']).write_bytes(canon(policy))
    _,out=invoke(root,request); decision=json.loads((out/'decision.json').read_text()); assert decision['reasons']==['HOOK_DIGEST_MISMATCH']

def test_corpus_verdict_and_duplicate_records_are_not_trusted(incident):
    """The snapshot cannot inject verdicts or ambiguous duplicate identities."""
    root,request,_=incident; records=json.loads((pathlib.Path(request['corpus'])/'records.json').read_text()); records[0]['verdict']='trusted'; (pathlib.Path(request['corpus'])/'records.json').write_bytes(canon(records))
    result,out=invoke(root,request); assert result.returncode==2 and not out.exists()

def test_output_replacement_and_digest_are_deterministic(incident):
    """Repeated verification removes stale files and produces the same evidence digest."""
    root,request,_=incident; _,out=invoke(root,request); first=(out/'decision.json').read_bytes(); (out/'stale').write_text('x'); _,out=invoke(root,request)
    assert not (out/'stale').exists() and (out/'decision.json').read_bytes()==first
    d=json.loads(first); evidence=dict(d); digest=evidence.pop('evidence_sha256'); assert digest==hashlib.sha256(canon(evidence)).hexdigest()

def test_health_endpoint_uses_fastify():
    """The required Fastify entrypoint retains its health endpoint."""
    source=(APP/'src/server.js').read_text(); package=json.loads((APP/'package.json').read_text())
    assert "Fastify" in source and package['dependencies']['fastify']=='5.10.0'
