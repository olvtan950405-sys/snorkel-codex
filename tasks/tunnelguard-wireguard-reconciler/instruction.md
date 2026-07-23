# Close authorization bypasses in the tunnelguard WireGuard security gate

An access-control review of the edge gateway at `/app` found that `tunnelguard` can grant network access to expired emergency users, compromised keys, peers outside their assigned address pools, and peers advertising routes they do not own. IPv4-mapped IPv6 spellings can also evade duplicate-address enforcement. The resulting WireGuard and nftables files look deployable, so these failures can silently expose protected services or redirect gateway traffic.

Harden the gate so every enabled peer is authenticated, authorized, assigned and routed according to the zero-trust contract. `tunnelguard` reads the gateway inventory from `/app/data/gateway.db`, access policy from `/app/data/access-policy.yaml`, and key-compromise and rotation evidence from the service selected by `KEY_EVENT_API_BASE`. The database, policy and output locations can also be selected through the environment-variable overrides in the contract. A default run must safely produce:

- `/app/out/wireguard/wg0.conf`
- `/app/out/firewall/tunnelguard.nft`
- `/app/out/audit/peer-access.json`
- `/app/out/audit/peer-access.md`

`/app/docs/access-policy-spec.md` is the authoritative security contract. It defines identity normalization, deny and emergency-access precedence, key-event replay, safe allocation, route ownership and conflicts, verdict precedence, and the exact enforcement and audit formats.

Implement the security controls under `/app/src`. Changing generated files or bundled evidence is not a remediation: the verifier rebuilds the Rust project and evaluates fresh gateway inventories and key histories. Supporting Python modules are permitted, but `/app/bin/tunnelguard` must remain the compiled entry point.
