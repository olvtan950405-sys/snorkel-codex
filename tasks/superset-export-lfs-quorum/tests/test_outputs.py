from __future__ import annotations
import hashlib, json, os, subprocess
from pathlib import Path
import duckdb, pytest

def run(*args, cwd=None, env=None, check=True):
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=check)

class Fixture:
    def __init__(self, root: Path, remote_name='policy-a.git'):
        self.root=root; self.work=root/'policy'; self.remotes=[root/remote_name, root/'policy-b.git']; self.source=root/'source'
        self.work.mkdir(); self.source.mkdir()
        for repo in (self.work, self.source):
            run('git','init','-q',str(repo)); run('git','config','user.name','Fixture',cwd=repo); run('git','config','user.email','f@invalid',cwd=repo)
        run('git','lfs','install','--local',cwd=self.work)
        (self.work/'.gitattributes').write_text('images/*.png filter=lfs diff=lfs merge=lfs -text\n')
        (self.work/'images').mkdir(); self.payload=b'generated thumbnail\x00bytes\n'; (self.work/'images/a.png').write_bytes(self.payload)
        (self.work/'policy.json').write_text('{"version":1,"dashboards":{"42":[5]}}\n')
        run('git','add','.',cwd=self.work); run('git','commit','-qm','release',cwd=self.work)
        self.commit=run('git','rev-parse','HEAD',cwd=self.work).stdout.strip(); run('git','tag','-a','v2.3.4','-m','release',cwd=self.work)
        for index, remote in enumerate(self.remotes):
            run('git','clone','-q','--bare',str(self.work),str(remote)); name=f'mirror{index}'; run('git','remote','add',name,str(remote),cwd=self.work); run('git','lfs','push','--all',name,cwd=self.work)
        e=os.environ.copy(); e['GIT_ALLOW_PROTOCOL']='file'; run('git','submodule','add','-q',str(self.remotes[0]),'vendor/policy',cwd=self.source,env=e)
        run('git','-C',str(self.source/'vendor/policy'),'checkout','-q',self.commit); run('git','add','.',cwd=self.source); run('git','commit','-qm','pin',cwd=self.source)
        self.db=root/'audit.duckdb'; c=duckdb.connect(str(self.db)); c.execute('CREATE TABLE export_audit(dashboard_id BIGINT, actor VARCHAR, decision VARCHAR, occurred_at TIMESTAMP)'); c.execute("INSERT INTO export_audit VALUES (42,'sam','allow',TIMESTAMP '2026-01-01')"); c.close()
        self.export=root/'export.json'; self.export.write_text(json.dumps({'dashboardId':42,'requestedBy':'sam','charts':[{'id':5,'thumbnail':'images/a.png','oid':hashlib.sha256(self.payload).hexdigest(),'size':len(self.payload)}]}))
        self.config=root/'worker.json'; self.write_config()

    def write_config(self, **changes):
        value={'policyRemotes':[str(x) for x in self.remotes],'policyRef':'refs/tags/v2.3.4','policyCommit':self.commit,'policySubmodule':'vendor/policy','auditDatabase':str(self.db)}; value.update(changes); self.config.write_text(json.dumps(value))

    def verdict(self):
        e=os.environ.copy(); e.update(EXPORT_GUARD_CONFIG=str(self.config),SOURCE_REPO=str(self.source))
        p=run('/app/bin/export-guard','--export',str(self.export),env=e,check=False)
        assert p.stderr == ''
        return p.returncode, json.loads(p.stdout), p.stdout

@pytest.fixture
def fx(tmp_path):
    return Fixture(tmp_path)

def test_dynamic_release_is_approved_canonically(fx):
    rc,data,out=fx.verdict(); assert rc==0
    assert data=={'charts':1,'dashboardId':42,'policyCommit':fx.commit,'status':'approved'}
    assert out==json.dumps(data,sort_keys=True,separators=(',',':'))+'\n'

def test_mutable_branch_is_never_accepted(fx):
    fx.write_config(policyRef='refs/heads/main'); assert fx.verdict()[1]=={'reasons':['POLICY_REF_INVALID'],'status':'rejected'}

def test_tag_commit_and_gitlink_must_both_match(fx):
    fx.write_config(policyCommit='0'*40); assert fx.verdict()[1]['reasons']==['POLICY_PIN_MISMATCH']

def test_at_least_two_distinct_mirrors_are_required(fx):
    fx.write_config(policyRemotes=[str(fx.remotes[0])]); assert fx.verdict()[1]['reasons']==['POLICY_QUORUM_FAILED']

def test_every_mirror_must_resolve_the_same_release(fx):
    run('git','--git-dir',str(fx.remotes[1]),'update-ref','-d','refs/tags/v2.3.4')
    assert fx.verdict()[1]['reasons']==['POLICY_QUORUM_FAILED']

def test_lfs_content_must_exist_on_every_mirror(fx):
    for object_file in (fx.remotes[1]/'lfs'/'objects').glob('*/*/*'):
        object_file.unlink()
    assert fx.verdict()[1]['reasons']==['THUMBNAIL_MISMATCH']

def test_latest_audit_decision_controls_approval(fx):
    c=duckdb.connect(str(fx.db)); c.execute("INSERT INTO export_audit VALUES (42,'sam','deny',TIMESTAMP '2026-02-01')"); c.close()
    assert fx.verdict()[1]=={'reasons':['AUDIT_DENIED'],'status':'rejected'}

@pytest.mark.parametrize('field,value,reason',[('oid','0'*64,'LFS_POINTER_INVALID'),('size',999,'LFS_POINTER_INVALID'),('thumbnail','../a.png','INVALID_EXPORT')])
def test_untrusted_thumbnail_metadata_is_rejected(fx,field,value,reason):
    doc=json.loads(fx.export.read_text()); doc['charts'][0][field]=value; fx.export.write_text(json.dumps(doc))
    assert reason in fx.verdict()[1]['reasons']

def test_policy_controls_chart_allowlist(fx):
    doc=json.loads(fx.export.read_text()); doc['charts'][0]['id']=99; fx.export.write_text(json.dumps(doc))
    assert fx.verdict()[1]=={'reasons':['CHART_NOT_ALLOWED'],'status':'rejected'}

def test_remote_shell_metacharacters_are_inert(tmp_path):
    fixture=Fixture(tmp_path,'remote;touch PWNED.git'); assert fixture.verdict()[0]==0
    assert not (tmp_path/'PWNED').exists() and not Path('/app/PWNED').exists()

def test_inputs_are_not_modified(fx):
    before=[hashlib.sha256(p.read_bytes()).digest() for p in (fx.export,fx.db,fx.config)]
    assert fx.verdict()[0]==0
    assert before==[hashlib.sha256(p.read_bytes()).digest() for p in (fx.export,fx.db,fx.config)]

def test_shipped_config_is_repaired():
    cfg=json.loads(Path('/app/config/worker.json').read_text()); assert len(cfg['policyRemotes']) >= 2 and cfg['policyRef'].startswith('refs/tags/v') and len(cfg['policyCommit'])==40
    p=run('/app/bin/export-guard','--export','/app/data/example-export.json',check=False); assert p.returncode==0
