use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

fn setting(name: &str, default: &str) -> PathBuf {
    PathBuf::from(env::var(name).unwrap_or_else(|_| default.to_string()))
}

fn jq(file: &Path, filter: &str) -> Result<String, String> {
    let out = Command::new("jq")
        .args(["-er", filter])
        .arg(file)
        .output()
        .map_err(|e| format!("cannot run jq: {e}"))?;
    if !out.status.success() {
        return Err(format!("invalid metadata {}", file.display()));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn sql(db: &Path, statement: &str) -> Result<String, String> {
    let out = Command::new("sqlite3")
        .arg(db)
        .arg(statement)
        .output()
        .map_err(|e| format!("cannot run sqlite3: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn sha256(path: &Path) -> Result<String, String> {
    let out = Command::new("sha256sum")
        .arg(path)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err("sha256sum failed".into());
    }
    Ok(String::from_utf8_lossy(&out.stdout)
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_string())
}

fn hex_decode(value: &str) -> Result<Vec<u8>, String> {
    if value.len() % 2 != 0 {
        return Err("odd hex".into());
    }
    (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&value[i..i + 2], 16).map_err(|_| "bad hex".into()))
        .collect()
}

fn signature_ok(metadata: &Path, public_hex: &str, signature_hex: &str, serial: usize) -> bool {
    let stem = format!("/tmp/repoguard-{}-{serial}", std::process::id());
    let canonical = PathBuf::from(format!("{stem}.json"));
    let public = PathBuf::from(format!("{stem}.der"));
    let signature = PathBuf::from(format!("{stem}.sig"));
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
    let mut message = rendered.stdout;
    if message.last() == Some(&b'\n') {
        message.pop();
    }
    let mut der = hex_decode("302a300506032b6570032100").unwrap();
    let raw = match hex_decode(public_hex) {
        Ok(value) => value,
        Err(_) => return false,
    };
    let sig = match hex_decode(signature_hex) {
        Ok(value) => value,
        Err(_) => return false,
    };
    der.extend(raw);
    if fs::write(&canonical, message).is_err()
        || fs::write(&public, der).is_err()
        || fs::write(&signature, sig).is_err()
    {
        return false;
    }
    let status = Command::new("openssl")
        .args([
            "pkeyutl", "-verify", "-pubin", "-keyform", "DER", "-rawin", "-inkey",
        ])
        .arg(&public)
        .arg("-in")
        .arg(&canonical)
        .arg("-sigfile")
        .arg(&signature)
        .status();
    let _ = fs::remove_file(canonical);
    let _ = fs::remove_file(public);
    let _ = fs::remove_file(signature);
    status.map(|s| s.success()).unwrap_or(false)
}

fn threshold_ok(metadata: &Path, root: &Path, role: &str) -> Result<bool, String> {
    let threshold: usize = jq(root, &format!(".signed.roles[\"{role}\"].threshold"))?
        .parse()
        .map_err(|_| "threshold")?;
    let rows = jq(metadata, ".signatures[] | [.keyid,.sig] | @tsv")?;
    let mut valid = 0usize;
    let mut serial = 0usize;
    for row in rows.lines() {
        let (keyid, signature) = match row.split_once('\t') {
            Some(value) => value,
            None => continue,
        };
        let authorized = jq(
            root,
            &format!(".signed.roles[\"{role}\"].keyids | index(\"{keyid}\") != null"),
        )? == "true";
        if !authorized {
            continue;
        }
        let public = jq(root, &format!(".signed.keys[\"{keyid}\"].public"))?;
        if signature_ok(metadata, &public, signature, serial) {
            valid += 1;
        }
        serial += 1;
    }
    // BUG: duplicate valid signatures currently count more than once.
    Ok(valid >= threshold)
}

fn fail(out: &Path, reason: &str) -> ExitCode {
    let _ = fs::create_dir_all(out);
    let body =
        format!("{{\"reason\":\"{reason}\",\"repository_status\":\"invalid\",\"targets\":[]}}\n");
    let _ = fs::write(out.join("report.json"), body);
    eprintln!("repoguard: {reason}");
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let repo = setting("REPOGUARD_REPOSITORY", "/app/repository");
    let trusted = setting("REPOGUARD_TRUSTED_ROOT", "/app/state/trusted-root.json");
    let db = setting("REPOGUARD_STATE_DB", "/app/state/trust.db");
    let out = setting("REPOGUARD_OUT", "/app/out");
    let root = repo.join("metadata/root.json");
    let timestamp = repo.join("metadata/timestamp.json");
    let snapshot = repo.join("metadata/snapshot.json");
    let targets = repo.join("metadata/targets.json");

    let result = (|| -> Result<(), String> {
        // BUG: a root rotation is accepted when only the candidate root authorizes it.
        if !threshold_ok(&root, &root, "root")? {
            return Err("root_threshold".into());
        }
        for (file, role) in [
            (&timestamp, "timestamp"),
            (&snapshot, "snapshot"),
            (&targets, "targets"),
        ] {
            if !threshold_ok(file, &root, role)? {
                return Err(format!("{role}_threshold"));
            }
        }
        let old: i64 = jq(&trusted, ".signed.version")?
            .parse()
            .map_err(|_| "root version")?;
        let new: i64 = jq(&root, ".signed.version")?
            .parse()
            .map_err(|_| "root version")?;
        if new != old + 1 {
            return Err("root_version".into());
        }

        let evaluation = jq(&repo.join("policy.json"), ".evaluation_time")?;
        for (file, role) in [
            (&root, "root"),
            (&timestamp, "timestamp"),
            (&snapshot, "snapshot"),
            (&targets, "targets"),
        ] {
            if jq(file, ".signed.expires")?.as_str() <= evaluation.as_str() {
                return Err(format!("{role}_expired"));
            }
            let version: i64 = jq(file, ".signed.version")?
                .parse()
                .map_err(|_| "version")?;
            let prior: i64 = sql(
                &db,
                &format!("SELECT version FROM accepted WHERE role='{role}';"),
            )?
            .parse()
            .unwrap_or(0);
            // BUG: equality is treated as rollback, so an idempotent rerun fails.
            if version <= prior {
                return Err(format!("{role}_rollback"));
            }
        }

        // BUG: state advances before descriptors, delegations, and target bytes are checked.
        for (file, role) in [
            (&root, "root"),
            (&timestamp, "timestamp"),
            (&snapshot, "snapshot"),
            (&targets, "targets"),
        ] {
            let version = jq(file, ".signed.version")?;
            sql(&db, &format!("INSERT INTO accepted(role,version) VALUES('{role}',{version}) ON CONFLICT(role) DO UPDATE SET version=excluded.version;"))?;
        }

        let expected_snapshot = jq(&timestamp, ".signed.meta[\"snapshot.json\"].hashes.sha256")?;
        // BUG: timestamp length and version commitments are ignored.
        if sha256(&snapshot)? != expected_snapshot {
            return Err("snapshot_descriptor".into());
        }
        let expected_targets = jq(&snapshot, ".signed.meta[\"targets.json\"].hashes.sha256")?;
        if sha256(&targets)? != expected_targets {
            return Err("targets_descriptor".into());
        }

        // The unfinished implementation reports files from top-level targets only.
        if out.exists() {
            fs::remove_dir_all(&out).map_err(|e| e.to_string())?;
        }
        fs::create_dir_all(out.join("authorizations")).map_err(|e| e.to_string())?;
        let paths = jq(&targets, ".signed.targets | keys[]")?;
        let mut entries = Vec::new();
        for path in paths.lines() {
            let artifact = repo.join("targets").join(path);
            let expected = jq(
                &targets,
                &format!(".signed.targets[\"{path}\"].hashes.sha256"),
            )?;
            let actual = sha256(&artifact)?;
            let status = if actual == expected {
                "trusted"
            } else {
                "quarantined"
            };
            let reason = if status == "trusted" {
                "null"
            } else {
                "\"target_mismatch\""
            };
            let entry = format!("{{\"path\":\"{path}\",\"reason\":{reason},\"role\":\"targets\",\"sha256\":\"{actual}\",\"status\":\"{status}\"}}");
            entries.push(entry.clone());
            if status == "trusted" {
                fs::write(
                    out.join("authorizations")
                        .join(path.replace('/', "__") + ".json"),
                    entry + "\n",
                )
                .map_err(|e| e.to_string())?;
            }
        }
        entries.sort();
        let report = format!(
            "{{\"repository_status\":\"trusted\",\"targets\":[{}]}}\n",
            entries.join(",")
        );
        fs::write(out.join("report.json"), report).map_err(|e| e.to_string())?;
        fs::write(
            out.join("audit.md"),
            "# Repository reconciliation\n\nReconciliation complete.\n",
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    })();
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => fail(&out, &reason),
    }
}
