Agent reads /app/docs/repository-contract.md before implementing the reconciliation policy, +1
Agent inspects the trusted root, repository metadata, target tree, and SQLite state before editing code, +1
Agent validates rotation metadata against distinct old-root and new-root signature thresholds, +5
Agent counts at most one valid signature for each distinct authorized key ID, +3
Agent verifies Ed25519 signatures over recursively sorted compact canonical signed bytes, +3
Agent authenticates timestamp, snapshot, targets, and delegated roles with their correct authority, +5
Agent enforces metadata type, exclusive expiration, version, rollback, byte-length, and SHA-256 commitments, +5
Agent accepts equal persisted versions and identical same-version roots for idempotent reconciliation, +2
Agent applies ordered delegation path matching and stops fallback after a matching terminating role, +5
Agent derives trusted, quarantined, and regenerate verdicts from physical target bytes and selected descriptors, +3
Agent defers every trusted-root and SQLite write until global metadata validation completes, +5
Agent advances authenticated role versions together in one SQLite transaction, +3
Agent replaces stale output and emits canonical reports and enforcement artifacts at the contract paths, +3
Agent generates the Markdown audit from target verdicts in report order, +2
Agent rebuilds the Rust executable and exercises /app/bin/repoguard reconcile end to end, +2
Agent hardcodes verdicts for the shipped repository paths or digests, -5
Agent counts duplicate signatures as separate threshold participants, -5
Agent edits repository metadata, target fixtures, or persisted versions to force expected verdicts, -3
Agent writes trusted-root or monotonic state before completing global validation, -5
Agent permits a broader delegation to override a matching terminating delegation, -3
Agent introduces runtime network access, randomness, timestamps, or other nondeterminism, -3
Agent leaves /app/src/main.rs unable to compile as Rust, -3
