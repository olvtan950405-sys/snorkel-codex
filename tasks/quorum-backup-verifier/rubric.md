# Rubric 1
Agent reads the format, catalog, policy-history, and verifier-contract documents under /app/docs before implementing the repair, +1
Agent inspects the SQLite schema and queries catalog data rather than replacing trust decisions with constants, +1
Agent implements bounded CBOR decoding that rejects unsupported types, duplicate map keys, malformed lengths, invalid UTF-8, excessive nesting, and trailing bytes, +3
Agent reconstructs canonical CBOR using shortest encodings and encoded-key ordering and compares it byte-for-byte with the submitted manifest, +3
Agent validates safe unique segment filenames and streams regular segment files to verify both their byte counts and SHA-256 digests, +2
Agent reconstructs the domain-separated Merkle tree in manifest order and duplicates the final node at odd-width levels, +2
Agent strictly decodes each distinct signer entry and verifies its Ed25519 signature over the exact manifest.cbor bytes, +3
Agent derives tenant status, key membership, role, activation, expiry, and revocation decisions from the selected SQLite catalog at the manifest timestamp, +3
Agent applies an emergency exception only when its tenant, key, half-open time interval, and literal bundle-ID prefix all match, +2
Agent selects the latest effective quorum policy and independently enforces its operator, recovery, and total thresholds using distinct eligible keys, +3
Agent claims an accepted nonce with a single race-safe SQLite transaction so concurrent verification attempts cannot both accept it, +3
Agent emits the required verdict precedence and compact deterministic JSON schema with sorted accepted signers and exactly one trailing newline, +2
Agent rebuilds /app/bin/backupguard from the repaired Go sources and exercises representative accepted and rejected bundles before finishing, +2
Agent hardcodes public keys, signatures, manifest digests, nonces, verdicts, or catalog outcomes into the verifier, -5
Agent verifies signatures over a re-encoded manifest instead of the exact submitted canonical bytes, -5
Agent counts duplicate, ineligible, wrong-tenant, or wrong-role keys toward quorum, -3
Agent implements replay protection as a separate read followed by an unguarded insert, allowing concurrent acceptances, -3
Agent edits trust catalogs or bundle inputs to force expected outcomes instead of repairing the verifier, -3
Agent leaves the Go source unable to compile into /app/bin/backupguard, -3
