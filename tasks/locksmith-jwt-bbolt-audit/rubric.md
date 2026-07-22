# Rubric 1
Agent reads `/app/docs/audit-contract.md` and inspects the fixture, requests, and module policy before implementing, +1
Agent implements the pipeline in Go and builds `/app/bin/locksmith-audit`, +2
Agent starts the configured fixture as a child with a fresh private bbolt path and the supplied master key, +3
Agent discovers the runtime listener and open database from the live process with lsof or strace rather than fixed values, +3
Agent strictly parses and replays the request fixture in order over loopback HTTP, +2
Agent fetches and strictly validates JWKS at the time each issued token is audited, +3
Agent selects exactly one Ed25519 key by `kid` and rejects duplicate, malformed, or incompatible JWKs, +3
Agent cryptographically verifies EdDSA JWT signatures without accepting attacker-selected algorithms or keys, +4
Agent enforces exact issuer, audience, header, identity, lease, and integer time claim requirements, +3
Agent observes signing-key rotation and correctly verifies tokens issued both before and after rotation, +2
Agent opens the discovered database read-only through bbolt and enumerates only the `leases` bucket, +3
Agent decrypts lease values with AES-256-GCM using the record key as authenticated additional data, +3
Agent strictly validates decrypted records and reconciles every record bidirectionally with one verified JWT, +4
Agent validates canonical module versions and rejects branches, mutable refs, tag/version disagreement, and duplicate coordinates, +3
Agent resolves only the exact remote tag with inert Git arguments and correctly peels annotated or lightweight tags, +3
Agent uses `go mod download -json` and binds its origin hash and ref to the independently resolved remote tag, +4
Agent emits the exact deterministically ordered, pretty-printed report with a trailing newline and no runtime secrets, +3
Agent writes the report atomically only after every runtime, token, database, and module check succeeds, +2
Agent always terminates and reaps the child and removes temporary databases and process state, +3
Agent verifies the pipeline end to end with inputs beyond the bundled fixture, +2
Agent decodes JWTs without signature verification or trusts `alg`, `kid`, claims, or JWK fields without strict validation, -5
Agent uses a fixed port/database path or trusts a path printed by the child instead of inspecting the process, -4
Agent reads bbolt bytes outside the bbolt API, skips AEAD authentication, or fails bidirectional reconciliation, -5
Agent accepts a branch, current tip, abbreviated commit, different tag, or unverifiable module origin, -5
Agent interpolates an untrusted path, ref, module, or remote into a shell command, -5
Agent hardcodes the shipped leases, keys, ports, commits, reports, or expected runtime values, -5
Agent modifies evidence inputs or replaces an existing report on any failed check, -4
Agent leaks the master key, token, database path, port, or temporary directory into the report, -3
