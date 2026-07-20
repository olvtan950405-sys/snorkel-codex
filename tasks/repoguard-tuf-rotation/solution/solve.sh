#!/usr/bin/env bash
set -euo pipefail

cd /app

# Install the reviewed implementation, then compile and exercise it.
cat > /app/src/main.rs <<'RS_EOF'
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

#[derive(Clone)]
struct Delegation {
    name: String,
    terminating: bool,
    threshold: usize,
    keyids: Vec<String>,
    patterns: Vec<String>,
    file: PathBuf,
}

#[derive(Clone)]
struct Record {
    length: Option<u64>,
    path: String,
    reason: Option<String>,
    role: Option<String>,
    sha256: Option<String>,
    status: String,
}

fn setting(name: &str, default: &str) -> PathBuf {
    PathBuf::from(env::var(name).unwrap_or_else(|_| default.into()))
}

fn command(program: &str, args: &[&str], file: Option<&Path>) -> Result<String, String> {
    let mut cmd = Command::new(program);
    cmd.args(args);
    if let Some(path) = file {
        cmd.arg(path);
    }
    let out = cmd
        .output()
        .map_err(|e| format!("cannot run {program}: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn jq(file: &Path, filter: &str) -> Result<String, String> {
    command("jq", &["-er", filter], Some(file)).map_err(|_| {
        format!(
            "malformed_metadata:{}",
            file.file_name().unwrap().to_string_lossy()
        )
    })
}
fn jq_opt(file: &Path, filter: &str) -> Option<String> {
    command("jq", &["-r", filter], Some(file))
        .ok()
        .filter(|s| s != "null" && !s.is_empty())
}
fn sql(db: &Path, statement: &str) -> Result<String, String> {
    command("sqlite3", &[db.to_str().unwrap(), statement], None)
        .map_err(|_| "state_database".into())
}
fn sha(path: &Path) -> Result<String, String> {
    Ok(command("sha256sum", &[], Some(path))?
        .split_whitespace()
        .next()
        .unwrap_or("")
        .into())
}
fn length(path: &Path) -> Result<u64, String> {
    fs::metadata(path)
        .map(|m| m.len())
        .map_err(|_| "missing_file".into())
}

fn hex(value: &str) -> Result<Vec<u8>, String> {
    if value.len() % 2 != 0 {
        return Err("bad_hex".into());
    }
    (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&value[i..i + 2], 16).map_err(|_| "bad_hex".into()))
        .collect()
}

fn signature_ok(metadata: &Path, public_hex: &str, signature_hex: &str, serial: usize) -> bool {
    let stem = format!("/tmp/repoguard-{}-{serial}", std::process::id());
    let msg = PathBuf::from(format!("{stem}.json"));
    let pubkey = PathBuf::from(format!("{stem}.der"));
    let sig = PathBuf::from(format!("{stem}.sig"));
    let rendered = Command::new("jq")
        .args(["-cS", ".signed"])
        .arg(metadata)
        .output();
    let rendered = match rendered {
        Ok(value) => value,
        Err(_) => return false,
    };
    if !rendered.status.success() {
        return false;
    }
    let mut bytes = rendered.stdout;
    if bytes.last() == Some(&b'\n') {
        bytes.pop();
    }
    let mut der = match hex("302a300506032b6570032100") {
        Ok(value) => value,
        Err(_) => return false,
    };
    let raw = match hex(public_hex) {
        Ok(value) => value,
        Err(_) => return false,
    };
    let signature = match hex(signature_hex) {
        Ok(value) => value,
        Err(_) => return false,
    };
    if raw.len() != 32 || signature.len() != 64 {
        return false;
    }
    der.extend(raw);
    if fs::write(&msg, bytes).is_err()
        || fs::write(&pubkey, der).is_err()
        || fs::write(&sig, signature).is_err()
    {
        return false;
    }
    let result = Command::new("openssl")
        .args([
            "pkeyutl", "-verify", "-pubin", "-keyform", "DER", "-rawin", "-inkey",
        ])
        .arg(&pubkey)
        .arg("-in")
        .arg(&msg)
        .arg("-sigfile")
        .arg(&sig)
        .output();
    let _ = fs::remove_file(msg);
    let _ = fs::remove_file(pubkey);
    let _ = fs::remove_file(sig);
    result.map(|o| o.status.success()).unwrap_or(false)
}

fn threshold_root(metadata: &Path, root: &Path, role: &str) -> Result<bool, String> {
    let needed: usize = jq(root, &format!(".signed.roles[\"{role}\"].threshold"))?
        .parse()
        .map_err(|_| "bad_threshold")?;
    let allowed: HashSet<String> = jq(root, &format!(".signed.roles[\"{role}\"].keyids[]"))?
        .lines()
        .map(str::to_string)
        .collect();
    threshold(metadata, needed, &allowed, |keyid| {
        jq(root, &format!(".signed.keys[\"{keyid}\"].public"))
    })
}

fn threshold_delegated(metadata: &Path, targets: &Path, role: &Delegation) -> Result<bool, String> {
    let allowed: HashSet<String> = role.keyids.iter().cloned().collect();
    threshold(metadata, role.threshold, &allowed, |keyid| {
        jq(
            targets,
            &format!(".signed.delegations.keys[\"{keyid}\"].public"),
        )
    })
}

fn threshold<F>(
    metadata: &Path,
    needed: usize,
    allowed: &HashSet<String>,
    lookup: F,
) -> Result<bool, String>
where
    F: Fn(&str) -> Result<String, String>,
{
    let rows = jq(metadata, ".signatures[] | [.keyid,.sig] | @tsv")?;
    let mut accepted = HashSet::new();
    for (serial, row) in rows.lines().enumerate() {
        let (keyid, sig) = match row.split_once('\t') {
            Some(value) => value,
            None => continue,
        };
        if !allowed.contains(keyid) || accepted.contains(keyid) {
            continue;
        }
        let public = lookup(keyid)?;
        if signature_ok(metadata, &public, sig, serial) {
            accepted.insert(keyid.to_string());
        }
    }
    Ok(accepted.len() >= needed)
}

fn descriptor(parent: &Path, name: &str, child: &Path, version: i64) -> Result<(), String> {
    let base = format!(".signed.meta[\"{name}\"]");
    let want_version: i64 = jq(parent, &format!("{base}.version"))?
        .parse()
        .map_err(|_| "descriptor_version")?;
    let want_length: u64 = jq(parent, &format!("{base}.length"))?
        .parse()
        .map_err(|_| "descriptor_length")?;
    let want_hash = jq(parent, &format!("{base}.hashes.sha256"))?;
    if want_version != version || want_length != length(child)? || want_hash != sha(child)? {
        return Err(format!("descriptor_mismatch:{name}"));
    }
    Ok(())
}

fn metadata_checks(
    file: &Path,
    role: &str,
    expected_type: &str,
    evaluation: &str,
    db: &Path,
) -> Result<i64, String> {
    if jq(file, ".signed._type")? != expected_type {
        return Err(format!("type_mismatch:{role}"));
    }
    if jq(file, ".signed.expires")?.as_str() <= evaluation {
        return Err(format!("expired:{role}"));
    }
    let version: i64 = jq(file, ".signed.version")?
        .parse()
        .map_err(|_| format!("bad_version:{role}"))?;
    if version < 1 {
        return Err(format!("bad_version:{role}"));
    }
    let prior: i64 = sql(
        db,
        &format!(
            "SELECT COALESCE((SELECT version FROM accepted WHERE role='{}'),0);",
            role.replace('\'', "")
        ),
    )?
    .parse()
    .unwrap_or(0);
    if version < prior {
        return Err(format!("rollback:{role}"));
    }
    Ok(version)
}

fn delegations(targets: &Path, meta: &Path) -> Result<Vec<Delegation>, String> {
    let rows=jq(targets,".signed.delegations.roles[]? | [.name,(.terminating|tostring),(.threshold|tostring),(.keyids|join(\",\")),(.paths|join(\",\"))] | @tsv").unwrap_or_default();
    let mut result = Vec::new();
    for row in rows.lines() {
        let fields: Vec<&str> = row.split('\t').collect();
        if fields.len() != 5 {
            return Err("bad_delegation".into());
        }
        result.push(Delegation {
            name: fields[0].into(),
            terminating: fields[1] == "true",
            threshold: fields[2].parse().map_err(|_| "bad_delegation")?,
            keyids: fields[3].split(',').map(str::to_string).collect(),
            patterns: fields[4].split(',').map(str::to_string).collect(),
            file: meta.join(format!("{}.json", fields[0])),
        });
    }
    Ok(result)
}

fn matches(pattern: &str, path: &str) -> bool {
    let p: Vec<&str> = pattern.split('/').collect();
    let s: Vec<&str> = path.split('/').collect();
    fn rec(p: &[&str], s: &[&str]) -> bool {
        if p.is_empty() {
            return s.is_empty();
        }
        if p[0] == "**" {
            return !s.is_empty() && (p.len() == 1 || rec(&p[1..], &s[1..]) || rec(p, &s[1..]));
        }
        if s.is_empty() {
            return false;
        }
        (p[0] == "*" || p[0] == s[0]) && rec(&p[1..], &s[1..])
    }
    rec(&p, &s)
}
fn target_row(file: &Path, path: &str) -> Option<(u64, String)> {
    let filter =
        format!(".signed.targets[\"{path}\"] | [(.length|tostring),.hashes.sha256] | @tsv");
    let row = jq_opt(file, &filter)?;
    let (n, h) = row.split_once('\t')?;
    Some((n.parse().ok()?, h.into()))
}
fn select(path: &str, targets: &Path, roles: &[Delegation]) -> Option<(String, u64, String)> {
    if let Some((n, h)) = target_row(targets, path) {
        return Some(("targets".into(), n, h));
    }
    for role in roles {
        if !role.patterns.iter().any(|p| matches(p, path)) {
            continue;
        }
        if let Some((n, h)) = target_row(&role.file, path) {
            return Some((role.name.clone(), n, h));
        }
        if role.terminating {
            return None;
        }
    }
    None
}
fn walk(base: &Path, current: &Path, out: &mut BTreeSet<String>) -> Result<(), String> {
    for entry in fs::read_dir(current).map_err(|_| "target_tree")? {
        let entry = entry.map_err(|_| "target_tree")?;
        let path = entry.path();
        if path.is_dir() {
            walk(base, &path, out)?
        } else if path.is_file() {
            out.insert(
                path.strip_prefix(base)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/"),
            );
        }
    }
    Ok(())
}
fn descriptor_paths(file: &Path) -> Vec<String> {
    jq(file, ".signed.targets | keys[]")
        .unwrap_or_default()
        .lines()
        .map(str::to_string)
        .collect()
}
fn escape(value: &str) -> String {
    let mut out = String::new();
    for c in value.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}
fn q(value: &str) -> String {
    format!("\"{}\"", escape(value))
}
fn opt(value: &Option<String>) -> String {
    value
        .as_ref()
        .map(|v| q(v))
        .unwrap_or_else(|| "null".into())
}
fn record_json(r: &Record) -> String {
    format!(
        "{{\"length\":{},\"path\":{},\"reason\":{},\"role\":{},\"sha256\":{},\"status\":{}}}",
        r.length
            .map(|n| n.to_string())
            .unwrap_or_else(|| "null".into()),
        q(&r.path),
        opt(&r.reason),
        opt(&r.role),
        opt(&r.sha256),
        q(&r.status)
    )
}

fn fail(out: &Path, reason: &str) -> ExitCode {
    let _ = fs::remove_dir_all(out);
    let _ = fs::create_dir_all(out);
    let _ = fs::write(
        out.join("report.json"),
        format!(
            "{{\"reason\":{},\"repository_status\":\"invalid\",\"targets\":[]}}\n",
            q(reason)
        ),
    );
    eprintln!("repoguard: {reason}");
    ExitCode::from(2)
}

fn run(repo: &Path, trusted: &Path, db: &Path, out: &Path) -> Result<(), String> {
    let meta = repo.join("metadata");
    let root = meta.join("root.json");
    let timestamp = meta.join("timestamp.json");
    let snapshot = meta.join("snapshot.json");
    let targets = meta.join("targets.json");
    let evaluation = jq(&repo.join("policy.json"), ".evaluation_time")?;
    let old: i64 = jq(trusted, ".signed.version")?
        .parse()
        .map_err(|_| "trusted_root_version")?;
    let new: i64 = jq(&root, ".signed.version")?
        .parse()
        .map_err(|_| "root_version")?;
    if new == old + 1 {
        if !threshold_root(&root, trusted, "root")? {
            return Err("old_root_threshold".into());
        }
    } else if new == old {
        if fs::read(trusted).map_err(|_| "trusted_root_read")?
            != fs::read(&root).map_err(|_| "root_read")?
        {
            return Err("root_same_version_mismatch".into());
        }
    } else {
        return Err("root_rotation_version".into());
    }
    if !threshold_root(&root, &root, "root")? {
        return Err("new_root_threshold".into());
    }
    let mut versions = BTreeMap::new();
    versions.insert(
        "root".to_string(),
        metadata_checks(&root, "root", "root", &evaluation, db)?,
    );
    for (file, role, kind) in [
        (&timestamp, "timestamp", "timestamp"),
        (&snapshot, "snapshot", "snapshot"),
        (&targets, "targets", "targets"),
    ] {
        if !threshold_root(file, &root, role)? {
            return Err(format!("threshold:{role}"));
        }
        versions.insert(
            role.into(),
            metadata_checks(file, role, kind, &evaluation, db)?,
        );
    }
    descriptor(&timestamp, "snapshot.json", &snapshot, versions["snapshot"])?;
    descriptor(&snapshot, "targets.json", &targets, versions["targets"])?;
    let roles = delegations(&targets, &meta)?;
    for role in &roles {
        if !threshold_delegated(&role.file, &targets, role)? {
            return Err(format!("threshold:{}", role.name));
        }
        let version = metadata_checks(&role.file, &role.name, "targets", &evaluation, db)?;
        descriptor(
            &snapshot,
            &format!("{}.json", role.name),
            &role.file,
            version,
        )?;
        versions.insert(role.name.clone(), version);
    }
    let base = repo.join("targets");
    let mut paths = BTreeSet::new();
    walk(&base, &base, &mut paths)?;
    for p in descriptor_paths(&targets) {
        paths.insert(p);
    }
    for role in &roles {
        for p in descriptor_paths(&role.file) {
            if role.patterns.iter().any(|pat| matches(pat, &p)) {
                paths.insert(p);
            }
        }
    }
    let mut records = Vec::new();
    for path in paths {
        if path.starts_with('/')
            || path
                .split('/')
                .any(|s| s.is_empty() || s == "." || s == "..")
        {
            return Err("unsafe_target_path".into());
        }
        let file = base.join(&path);
        let chosen = select(&path, &targets, &roles);
        let exists = file.is_file();
        let (role, want_len, want_hash) = match chosen {
            Some((r, n, h)) => (Some(r), Some(n), Some(h)),
            None => (None, None, None),
        };
        let actual_len = if exists { Some(length(&file)?) } else { None };
        let actual_hash = if exists { Some(sha(&file)?) } else { None };
        let (status, reason) = if role.is_none() {
            ("quarantined", Some("unclaimed_target".into()))
        } else if !exists {
            ("regenerate", Some("target_missing".into()))
        } else if actual_len != want_len || actual_hash != want_hash {
            ("quarantined", Some("target_mismatch".into()))
        } else {
            ("trusted", None)
        };
        records.push(Record {
            length: actual_len,
            path,
            reason,
            role,
            sha256: actual_hash,
            status: status.into(),
        });
    }
    let mut tx = "BEGIN IMMEDIATE;".to_string();
    for (role, version) in &versions {
        tx.push_str(&format!("INSERT INTO accepted(role,version) VALUES('{}',{}) ON CONFLICT(role) DO UPDATE SET version=MAX(version,excluded.version);",role,version));
    }
    tx.push_str("COMMIT;");
    sql(db, &tx)?;
    let temp = trusted.with_extension("json.tmp");
    fs::copy(&root, &temp).map_err(|_| "trusted_root_write")?;
    fs::rename(&temp, trusted).map_err(|_| "trusted_root_write")?;
    let _ = fs::remove_dir_all(out);
    for dir in ["authorizations", "quarantine", "regeneration"] {
        fs::create_dir_all(out.join(dir)).map_err(|_| "output_write")?
    }
    let mut encoded = Vec::new();
    for r in &records {
        let body = record_json(r) + "\n";
        let dir = match r.status.as_str() {
            "trusted" => "authorizations",
            "quarantined" => "quarantine",
            _ => "regeneration",
        };
        fs::write(
            out.join(dir).join(r.path.replace('/', "__") + ".json"),
            body,
        )
        .map_err(|_| "output_write")?;
        encoded.push(record_json(r));
    }
    let version_json = versions
        .iter()
        .map(|(k, v)| format!("{}:{}", q(k), v))
        .collect::<Vec<_>>()
        .join(",");
    fs::write(out.join("report.json"),format!("{{\"metadata_versions\":{{{version_json}}},\"repository_status\":\"trusted\",\"targets\":[{}]}}\n",encoded.join(","))).map_err(|_|"output_write")?;
    let mut audit = "# Repository reconciliation\n\n".to_string();
    for r in &records {
        let detail = r.reason.as_ref().or(r.role.as_ref()).unwrap();
        audit.push_str(&format!("- `{}`: {} ({})\n", r.path, r.status, detail));
    }
    fs::write(out.join("audit.md"), audit).map_err(|_| "output_write")?;
    Ok(())
}

fn main() -> ExitCode {
    let repo = setting("REPOGUARD_REPOSITORY", "/app/repository");
    let trusted = setting("REPOGUARD_TRUSTED_ROOT", "/app/state/trusted-root.json");
    let db = setting("REPOGUARD_STATE_DB", "/app/state/trust.db");
    let out = setting("REPOGUARD_OUT", "/app/out");
    match run(&repo, &trusted, &db, &out) {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => fail(&out, &reason),
    }
}
RS_EOF

rustc --edition=2021 -O /app/src/main.rs -o /app/target/repoguard
/app/bin/repoguard reconcile
jq -e '.repository_status == "trusted" and (.targets | length == 6)' /app/out/report.json >/dev/null
