# Repair the tunnelguard WireGuard access reconciler

The edge gateway at `/app` was migrated to a zero-trust policy, but its `tunnelguard` reconciler was left half-finished. It still emits plausible WireGuard and nftables configuration even when peers have expired access, compromised keys, overlapping routes, or addresses that do not belong to their allocation pool.

`tunnelguard` reads peers, address pools, reservations, and group membership from `/app/data/gateway.db`; policy from `/app/data/access-policy.yaml`; and key events from the HTTP service selected by `KEY_EVENT_API_BASE`. It must reconcile that state at the policy's fixed evaluation instant and write:

- `/app/out/wireguard/wg0.conf`
- `/app/out/firewall/tunnelguard.nft`
- `/app/out/audit/peer-access.json`
- `/app/out/audit/peer-access.md`

The complete contract is `/app/docs/access-policy-spec.md`. It defines address normalization, policy precedence, emergency-access boundaries, key-event semantics, allocation, route conflicts, verdict precedence, and the exact output schemas. Treat it as authoritative.

Repair the implementation under `/app/src`. The verifier rebuilds the Rust project, so fixes must live in source rather than generated artifacts. Supporting Python modules are permitted, but `/app/bin/tunnelguard` must remain the compiled runnable entry point and must work for any database, policy, and key-event service matching the contract—not only the shipped example.
