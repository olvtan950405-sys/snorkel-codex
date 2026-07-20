//! Half-finished gateway reconciler. The output plumbing works, but several
//! policy decisions intentionally use migration-era shortcuts.

use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::Path;
use std::process::Command;

#[derive(Clone, Default)]
struct Peer {
    id: String,
    key: String,
    previous: String,
    pool: String,
    address: String,
    groups: Vec<String>,
    routes: Vec<String>,
    services: Vec<String>,
    status: String,
}

fn sql(db: &str, query: &str) -> Result<Vec<Vec<String>>, String> {
    let out = Command::new("sqlite3")
        .args(["-separator", "\t", "-noheader", db, query])
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).into_owned());
    }
    Ok(String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(|line| line.split('\t').map(str::to_owned).collect())
        .collect())
}

fn list_value(line: &str) -> Vec<String> {
    line.split_once('[')
        .and_then(|(_, tail)| tail.split_once(']'))
        .map(|(body, _)| {
            body.split(',')
                .map(|s| s.trim().trim_matches('"').to_owned())
                .filter(|s| !s.is_empty())
                .collect()
        })
        .unwrap_or_default()
}

fn policy(path: &str) -> Result<(String, u16, BTreeMap<String, (Vec<String>, Vec<String>)>, BTreeMap<String, (String, u16)>), String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut at = String::new();
    let mut port = 0;
    let mut section = "";
    let mut current = String::new();
    let mut groups: BTreeMap<String, (Vec<String>, Vec<String>)> = BTreeMap::new();
    let mut services = BTreeMap::new();
    for line in text.lines() {
        if let Some(v) = line.strip_prefix("evaluate_at: ") { at = v.to_owned(); }
        if let Some(v) = line.strip_prefix("listen_port: ") { port = v.parse().map_err(|_| "bad port")?; }
        if line == "groups:" { section = "groups"; continue; }
        if line == "services:" { section = "services"; continue; }
        if section == "groups" && line.starts_with("  ") && !line.starts_with("    ") && line.ends_with(':') {
            current = line.trim().trim_end_matches(':').to_owned();
            groups.entry(current.clone()).or_default();
        } else if section == "groups" && line.trim_start().starts_with("allow:") {
            groups.entry(current.clone()).or_default().0 = list_value(line);
        } else if section == "groups" && line.trim_start().starts_with("deny:") {
            groups.entry(current.clone()).or_default().1 = list_value(line);
        } else if section == "services" && line.starts_with("  ") {
            let (name, rest) = line.trim().split_once(':').ok_or("bad service")?;
            let cidr = rest.split("cidr:").nth(1).and_then(|s| s.split(',').next()).unwrap_or("").trim().trim_matches(|c| c == '"' || c == ' ' || c == '{').to_owned();
            let p = rest.split("port:").nth(1).unwrap_or("0").trim().trim_end_matches('}').parse().map_err(|_| "bad service port")?;
            services.insert(name.to_owned(), (cidr, p));
        }
    }
    Ok((at, port, groups, services))
}

fn get_events(base: &str, peer: &str) -> Result<String, String> {
    let target = base.strip_prefix("http://").ok_or("only http fixture endpoints are supported")?;
    let (host_port, prefix) = target.split_once('/').unwrap_or((target, ""));
    let mut stream = TcpStream::connect(host_port).map_err(|e| e.to_string())?;
    let path = format!("/{}/v1/events?peer_id={}", prefix.trim_matches('/'), peer);
    write!(stream, "GET {path} HTTP/1.0\r\nHost: {host_port}\r\n\r\n").map_err(|e| e.to_string())?;
    let mut response = String::new();
    stream.read_to_string(&mut response).map_err(|e| e.to_string())?;
    if !response.starts_with("HTTP/1.0 200") && !response.starts_with("HTTP/1.1 200") { return Err("event API failure".into()); }
    Ok(response.split("\r\n\r\n").nth(1).unwrap_or("").to_owned())
}

fn esc(value: &str) -> String { value.replace('\\', "\\\\").replace('"', "\\\"") }

fn main() -> Result<(), String> {
    let db = env::var("TUNNELGUARD_DB").unwrap_or_else(|_| "/app/data/gateway.db".into());
    let policy_path = env::var("TUNNELGUARD_POLICY").unwrap_or_else(|_| "/app/data/access-policy.yaml".into());
    let out = env::var("TUNNELGUARD_OUT").unwrap_or_else(|_| "/app/out".into());
    let api = env::var("KEY_EVENT_API_BASE").map_err(|_| "KEY_EVENT_API_BASE is required")?;
    let (at, listen_port, group_policy, service_policy) = policy(&policy_path)?;
    let mut peers = BTreeMap::<String, Peer>::new();
    for row in sql(&db, "SELECT peer_id,public_key,coalesce(previous_key,''),pool,address FROM peers WHERE enabled=1 ORDER BY peer_id")? {
        peers.insert(row[0].clone(), Peer { id: row[0].clone(), key: row[1].clone(), previous: row[2].clone(), pool: row[3].clone(), address: row[4].clone(), status: "active".into(), ..Peer::default() });
    }
    for row in sql(&db, "SELECT peer_id,group_name FROM memberships ORDER BY peer_id,group_name")? {
        if let Some(p) = peers.get_mut(&row[0]) { p.groups.push(row[1].clone()); }
    }
    for row in sql(&db, "SELECT peer_id,cidr FROM routes ORDER BY peer_id,cidr")? {
        if let Some(p) = peers.get_mut(&row[0]) { p.routes.push(row[1].clone()); }
    }
    let pools: BTreeMap<String, String> = sql(&db, "SELECT name,cidr FROM pools")?.into_iter().map(|r| (r[0].clone(), r[1].clone())).collect();
    let mut used = BTreeSet::new();
    for peer in peers.values_mut() {
        // Migration shortcuts: textual containment, allow-first policy, first
        // staged key, and duplicate-address detection before normalization.
        if !pools.get(&peer.pool).map(|cidr| peer.address.starts_with(cidr.split('.').next().unwrap_or(""))).unwrap_or(false) {
            peer.status = "quarantined".into();
        }
        if !used.insert(peer.address.clone()) && peer.status == "active" { peer.status = "address_conflict".into(); }
        for group in &peer.groups {
            if let Some((allow, deny)) = group_policy.get(group) {
                peer.services.extend(allow.clone());
                peer.services.retain(|s| !deny.contains(s) || allow.contains(s));
            }
        }
        peer.services.sort(); peer.services.dedup();
        if peer.services.is_empty() && peer.status == "active" { peer.status = "policy_denied".into(); }
        let events = get_events(&api, &peer.id);
        match events {
            Err(_) => peer.status = "quarantined".into(),
            Ok(body) if body.contains("compromised") && body.contains(&format!("\"key\":\"{}\"", peer.key)) => peer.status = "key_revoked".into(),
            Ok(body) if body.contains("rotated") && !peer.previous.is_empty() => peer.status = "rotate_key".into(),
            _ => {}
        }
        peer.routes.retain(|route| service_policy.values().any(|(cidr, _)| route.starts_with(cidr.split('.').next().unwrap_or(""))));
    }
    fs::create_dir_all(format!("{out}/wireguard")).map_err(|e| e.to_string())?;
    fs::create_dir_all(format!("{out}/firewall")).map_err(|e| e.to_string())?;
    fs::create_dir_all(format!("{out}/audit")).map_err(|e| e.to_string())?;
    let mut wg = format!("[Interface]\nListenPort = {listen_port}\n");
    let mut nft = "table inet tunnelguard {\n".to_owned();
    let mut md = format!("# tunnelguard peer-access audit\n\nEvaluated at: `{at}`\n\n| Peer | Status | Address | Services | Routes |\n|---|---|---|---|---|\n");
    let mut peer_json = Vec::new();
    let statuses = ["access_expired","active","address_conflict","key_revoked","policy_denied","quarantined","rotate_key","route_conflict"];
    let mut counts: BTreeMap<&str, usize> = statuses.into_iter().map(|s| (s, 0)).collect();
    for p in peers.values() {
        *counts.get_mut(p.status.as_str()).expect("known status") += 1;
        let service_json = p.services.iter().map(|s| format!("\"{}\"", esc(s))).collect::<Vec<_>>().join(",");
        let route_json = p.routes.iter().map(|s| format!("\"{}\"", esc(s))).collect::<Vec<_>>().join(",");
        peer_json.push(format!("{{\"allowed_services\":[{service_json}],\"assigned_address\":\"{}\",\"peer_id\":\"{}\",\"public_key\":\"{}\",\"routes\":[{route_json}],\"status\":\"{}\"}}", esc(&p.address), esc(&p.id), esc(&p.key), esc(&p.status)));
        md.push_str(&format!("| {} | {} | {} | {} | {} |\n", p.id, p.status, p.address, if p.services.is_empty() { "-".into() } else { p.services.join(", ") }, if p.routes.is_empty() { "-".into() } else { p.routes.join(", ") }));
        if p.status == "active" {
            wg.push_str(&format!("\n[Peer]\n# peer_id = {}\nPublicKey = {}\nAllowedIPs = {}/{}{}\n", p.id, p.key, p.address, if p.address.contains(':') {128} else {32}, if p.routes.is_empty() {String::new()} else {format!(", {}", p.routes.join(", "))}));
            for service in &p.services {
                let (cidr, port) = &service_policy[service];
                nft.push_str(&format!("  set peer_{}_{} {{ type {}_addr; elements = {{ {} }} # {}:{} }}\n", p.id, service, if p.address.contains(':') {"ipv6"} else {"ipv4"}, p.address, cidr, port));
            }
        }
    }
    nft.push_str("}\n");
    let peers_value = format!("[{}]", peer_json.join(","));
    let temp = format!("{out}/audit/.peers"); fs::write(&temp, &peers_value).map_err(|e| e.to_string())?;
    let digest = Command::new("sha256sum").arg(&temp).output().map_err(|e| e.to_string())?;
    let digest = String::from_utf8_lossy(&digest.stdout).split_whitespace().next().unwrap_or("").to_owned();
    let count_json = counts.iter().map(|(k,v)| format!("\"{k}\":{v}")).collect::<Vec<_>>().join(",");
    let report = format!("{{\"counts\":{{{count_json}}},\"evaluate_at\":\"{}\",\"peers\":{},\"sha256\":\"{}\"}}\n", esc(&at), peers_value, digest);
    fs::write(format!("{out}/wireguard/wg0.conf"), wg).map_err(|e| e.to_string())?;
    fs::write(format!("{out}/firewall/tunnelguard.nft"), nft).map_err(|e| e.to_string())?;
    fs::write(format!("{out}/audit/peer-access.json"), report).map_err(|e| e.to_string())?;
    fs::write(format!("{out}/audit/peer-access.md"), md).map_err(|e| e.to_string())?;
    let _ = fs::remove_file(temp);
    if !Path::new(&format!("{out}/audit/peer-access.json")).exists() { return Err("missing report".into()); }
    Ok(())
}
