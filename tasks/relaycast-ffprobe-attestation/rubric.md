# Rubric

1. **Safe probing (20%)**: invokes FFprobe without a shell, confines resolved media paths to `MEDIA_ROOT`, rejects symlinks/non-regular files and malformed requests, and validates the complete FFprobe shape.
2. **Canonical records (15%)**: applies the specified stream ordering, integer/rational normalization, field allowlist, compact JSON encoding, and SHA-256 digest.
3. **GraphML and signature verification (20%)**: strictly parses the documented graph, rejects duplicate/missing/unknown data, decodes the graph public key, and verifies every Ed25519 edge message with the probe digest and path binding.
4. **Merkle/report determinism (20%)**: sorts edges, constructs domain-separated leaves/nodes with the odd-node rule, and emits the exact canonical report schema and bytes.
5. **API and failures (15%)**: both Gin endpoints work, status/error envelopes follow the contract, attestations are atomic, and invalid evidence never produces a success report.
6. **Offline pipeline (10%)**: `relaycast reproduce` and `make reproduce` rebuild and operate from configurable local paths without a network dependency.
