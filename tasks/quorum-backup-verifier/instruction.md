# Restore quorum verification for GlacierVault backup manifests

GlacierVault's offline verifier in `/app` currently accepts unverified backup bundles. Repair the Go code so `go build -o /app/bin/backupguard ./cmd/backupguard` produces `/app/bin/backupguard verify --bundle <directory> --catalog <sqlite-file> --out <json-file>`. Implement the canonical-CBOR and Ed25519 rules in `/app/docs/bundle-format.md`, including streamed segment hashing and Merkle-root validation.

Enforce the temporal trust, role quorum, exception, and replay rules established by `/app/docs/policy-history/`, using only the selected SQLite catalog. Follow the verdict precedence and canonical JSON contract in `/app/docs/verifier-contract.md`. Acceptance must record the nonce and manifest digest atomically so concurrent claims produce at most one acceptance; rejections must not mutate the catalog. Keep the verifier offline, deterministic, and safe for malformed input.
