from pathlib import Path
import hashlib, json, os, subprocess
import duckdb

def run(*args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, stdout=subprocess.DEVNULL)

app = Path('/app'); work = Path('/tmp/policy-work')
remotes = [Path('/srv/policy-remotes/export-policy-a.git'), Path('/srv/policy-remotes/export-policy-b.git')]
work.mkdir(parents=True)
run('git', 'init', '-q', str(work)); run('git', 'config', 'user.name', 'Fixture', cwd=work); run('git', 'config', 'user.email', 'fixture@example.invalid', cwd=work); run('git', 'lfs', 'install', '--local', cwd=work)
(work / '.gitattributes').write_text('thumbnails/*.png filter=lfs diff=lfs merge=lfs -text\n'); (work / 'thumbnails').mkdir()
payload = b'chart eleven image\n'; (work / 'thumbnails/chart-11.png').write_bytes(payload); (work / 'policy.json').write_text('{"version":1,"dashboards":{"7":[11]}}\n')
run('git', 'add', '.', cwd=work); run('git', 'commit', '-qm', 'policy release', cwd=work)
commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=work, text=True).strip(); run('git', 'tag', '-a', 'v1.0.0', '-m', 'release', cwd=work)
remotes[0].parent.mkdir(parents=True)
for index, remote in enumerate(remotes):
    run('git', 'clone', '-q', '--bare', str(work), str(remote))
    name = f'mirror{index}'
    run('git', 'remote', 'add', name, str(remote), cwd=work)
    run('git', 'lfs', 'push', '--all', name, cwd=work)
run('git', 'init', '-q', str(app)); run('git', 'config', 'user.name', 'Fixture', cwd=app); run('git', 'config', 'user.email', 'fixture@example.invalid', cwd=app)
env = os.environ.copy(); env['GIT_ALLOW_PROTOCOL'] = 'file'; run('git', 'submodule', 'add', '-q', str(remotes[0]), 'vendor/policy-pack', cwd=app, env=env); run('git', '-C', str(app / 'vendor/policy-pack'), 'checkout', '-q', commit)
config = json.loads((app/'config/worker.json').read_text()); config.update(policyRef='refs/heads/main', policyCommit='FOLLOW_BRANCH', policyRemotes=[str(x) for x in remotes]); (app/'config/worker.json').write_text(json.dumps(config, indent=2)+'\n')
export = json.loads((app/'data/example-export.json').read_text()); export['charts'][0].update(oid=hashlib.sha256(payload).hexdigest(), size=len(payload)); (app/'data/example-export.json').write_text(json.dumps(export, separators=(',',':'))+'\n')
con = duckdb.connect(str(app/'data/audit.duckdb')); con.execute('CREATE TABLE export_audit(dashboard_id BIGINT, actor VARCHAR, decision VARCHAR, occurred_at TIMESTAMP)'); con.execute("INSERT INTO export_audit VALUES (7, 'alice', 'allow', TIMESTAMP '2026-01-01 00:00:00')"); con.close()
run('git', 'add', '.', cwd=app); run('git', 'commit', '-qm', 'broken export worker', cwd=app)
