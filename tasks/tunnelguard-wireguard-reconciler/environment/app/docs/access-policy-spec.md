# tunnelguard access-policy contract

All decisions use the RFC 3339 UTC instant `evaluate_at` in the selected policy file. Inputs are immutable evidence; tunnelguard may only replace the selected output directory.

## Security objective

This contract is the gateway's authorization boundary. A peer must never enter enforcement through alternate IP spelling, an expired grant, a denied service, compromised or inconsistent key evidence, an address collision, an unauthorized route, or a route overlapping an earlier admitted peer. Ambiguous or malformed security evidence fails closed according to the verdict precedence below. Audit output is evidence only; a rejected peer must be absent from both WireGuard and nftables configuration.

## Runtime configuration

`/app/bin/tunnelguard` takes no command-line arguments. It reads these environment variables:

- `TUNNELGUARD_DB`: SQLite inventory path; default `/app/data/gateway.db`.
- `TUNNELGUARD_POLICY`: YAML policy path; default `/app/data/access-policy.yaml`.
- `TUNNELGUARD_OUT`: output directory; default `/app/out`.
- `KEY_EVENT_API_BASE`: required base URL for the key-event service, without a required trailing slash.

Every output path named below is relative to the selected `TUNNELGUARD_OUT`. The program must honor all four settings together so an operator can reconcile an alternate snapshot without changing `/app/data` or `/app/out`.

## Inputs

The SQLite database contains:

- `pools(name TEXT PRIMARY KEY, cidr TEXT NOT NULL)`
- `reservations(pool TEXT, address TEXT, reason TEXT)`
- `peers(peer_id TEXT PRIMARY KEY, public_key TEXT, previous_key TEXT, pool TEXT, address TEXT, enabled INTEGER)`
- `memberships(peer_id TEXT, group_name TEXT)`
- `routes(peer_id TEXT, cidr TEXT)`
- `emergency_access(peer_id TEXT, service TEXT, starts_at TEXT, expires_at TEXT)`

The YAML policy uses this deliberately small schema:

```yaml
evaluate_at: 2026-07-01T12:00:00Z
interface: wg0
listen_port: 51820
groups:
  engineers:
    allow: ["git", "metrics"]
    deny: ["prod-db"]
services:
  git: {cidr: "10.80.10.0/24", port: 443}
  metrics: {cidr: "10.80.20.0/24", port: 9090}
  prod-db: {cidr: "10.80.30.0/24", port: 5432}
```

Names and IDs are non-empty ASCII strings. Timestamps have exactly `YYYY-MM-DDTHH:mm:ssZ`. Ports are 1..65535. CIDRs and addresses may be IPv4, IPv6, or IPv4-mapped IPv6.

`GET {KEY_EVENT_API_BASE}/v1/events?peer_id=<percent-encoded-id>` returns a JSON array sorted arbitrarily. Each object is one of:

```json
{"kind":"compromised","key":"base64-key","at":"2026-06-01T00:00:00Z"}
{"kind":"rotated","old_key":"base64-key","new_key":"base64-key","at":"2026-06-02T00:00:00Z"}
```

Query exactly once for every enabled peer and never for a disabled peer. A non-200 response, malformed JSON, or malformed event is evidence failure and quarantines that peer.

## Address and CIDR rules

Parse addresses numerically. Convert IPv4-mapped IPv6 (`::ffff:a.b.c.d`) to IPv4 immediately after parsing and before every later operation, including address-family checks, pool membership, reservation lookup, allocation bookkeeping, duplicate/conflict detection and serialization. A mapped address such as `::ffff:10.70.0.2` is therefore an IPv4 address inside an IPv4 pool and conflicts with another peer configured as `10.70.0.2`; it must not be rejected merely because its input spelling is IPv6. Serialize addresses in compressed lowercase form and CIDRs at their masked network address.

A peer address is valid only when it is a usable member of its named pool and is not reserved. For IPv4, the network and broadcast addresses are unusable except that both addresses of a `/31` and the sole address of a `/32` are usable. Every IPv6 address in a pool is usable. If the configured address is invalid, allocate the numerically lowest usable, unreserved address not assigned to another enabled peer. If none exists, the peer is `quarantined`.

Address conflicts are resolved before route containment is evaluated. After normalizing every enabled peer's configured address, process peers by `peer_id` byte order; the first peer keeps a duplicated normalized address and each later peer receives `address_conflict`. An `address_conflict` peer retains that verdict even if one of its stored routes would fail containment.

For a peer that survives the key and access-policy verdicts and does not have an address conflict, normalize and de-duplicate its routes. Every route must be wholly contained by one of the service CIDRs that peer may access. **If any configured route is not wholly contained by an effectively allowed service CIDR, that peer is `quarantined`; silently dropping the unauthorized route is not permitted.** Peers already rejected by an earlier verdict do not advertise routes, so their stored routes do not replace that earlier verdict. Two remaining active candidates may not advertise overlapping routes. Process candidates by `peer_id` byte order; the first keeps an overlapping route and each later peer becomes `route_conflict`. Identical networks overlap.

## Access policy

Group names are combined in byte order. A service is allowed when at least one group allows it and no group denies it. Deny always wins, regardless of group order.

Emergency access grants one named service only when `starts_at <= evaluate_at < expires_at`. It overrides a group deny while active. The start is inclusive and expiry is exclusive. An invalid interval (`starts_at >= expires_at`) is ignored.

## Key state

Events after `evaluate_at` have no effect. Apply the remaining events by `(at, kind)` byte order, where `compromised` sorts before `rotated` at the same instant.

A current public key is revoked if it was compromised at or before evaluation and no later rotation event moved that exact key to the peer's current key. A peer whose current key differs from its most recent applicable rotation target is `rotate_key` when that target equals `previous_key`; otherwise its evidence is inconsistent and it is `quarantined`. A key compromised at the exact rotation instant remains compromised because compromise is applied first and the rotation moves authority to the new key.

## Verdict precedence

Each enabled peer receives exactly one status; disabled peers are omitted. First applicable status wins:

1. `quarantined`: malformed/unavailable event evidence, inconsistent key history, unknown pool, no allocatable address, unknown group/service reference, or invalid input other than route containment, which is evaluated after normalized `address_conflict` detection as described above.
2. `key_revoked`: the effective current key is compromised.
3. `rotate_key`: a valid latest rotation target is staged as `previous_key` but is not current.
4. `access_expired`: the peer has emergency rows but none active and has no group-derived allowed services.
5. `policy_denied`: it has no effective allowed services.
6. `address_conflict`: its configured address duplicates another enabled peer's configured address after normalization. Process by `peer_id`; the first keeps it. This verdict is determined before route-containment validation and is not replaced by a route-based `quarantined` verdict.
7. `route_conflict`: one of its normalized routes overlaps a route retained by an earlier active peer.
8. `active`.

Only `active` peers appear in enforcement configuration. A valid replacement address is allocated before the conflict checks and appears as `assigned_address`.

## Canonical audit JSON

`/app/out/audit/peer-access.json` is compact UTF-8 JSON with object keys recursively sorted, exactly one trailing newline, and exactly:

```json
{"counts":{"access_expired":0,"active":0,"address_conflict":0,"key_revoked":0,"policy_denied":0,"quarantined":0,"rotate_key":0,"route_conflict":0},"evaluate_at":"...","peers":[{"allowed_services":["git"],"assigned_address":"10.70.0.2","peer_id":"alice","public_key":"...","routes":["10.80.10.0/24"],"status":"active"}],"sha256":"..."}
```

`peers` is ordered by `peer_id`; its arrays are sorted and de-duplicated. All eight count keys are present. `sha256` is the lowercase SHA-256 of the canonical bytes of the `peers` array alone. Reformatting equivalent addresses or reordering input rows must not change output bytes.

## Enforcement files

`/app/out/wireguard/wg0.conf` begins with `[Interface]`, then `ListenPort = <port>`. For each active peer in `peer_id` order append a blank line and:

```ini
[Peer]
# peer_id = alice
PublicKey = <key>
AllowedIPs = <assigned-address>/32, <sorted routes>
```

Use `/128` for IPv6 addresses. Omit the comma and route portion when there are no routes. End with one newline.

`/app/out/firewall/tunnelguard.nft` begins `table inet tunnelguard {`, contains one `set peer_<safe-id>_<service>` for each active peer/service pair in sorted order, and ends `}`. A safe ID replaces every non-ASCII-alphanumeric byte with `_`. The set line is exactly `  set peer_<id>_<service> { type ipv4_addr; elements = { <address> } # <cidr>:<port> }`; use `ipv6_addr` for IPv6 peers. End with one newline.

`/app/out/audit/peer-access.md` contains a title, evaluation instant, and a table sorted by peer ID:

```markdown
# tunnelguard peer-access audit

Evaluated at: `2026-07-01T12:00:00Z`

| Peer | Status | Address | Services | Routes |
|---|---|---|---|---|
| alice | active | 10.70.0.2 | git | 10.80.10.0/24 |
```

Use `-` for an empty address or list and end with one newline.
