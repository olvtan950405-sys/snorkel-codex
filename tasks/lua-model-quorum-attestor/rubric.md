Agent runs the broken model-attestor and inspects the conflicted manifest before editing, +1
Agent reads /app/docs/release-attestation.md and inspects the annotated tags and committed LFS pointers, +1
Agent removes the rebase conflicts from both /app/release_attestor.lua and /app/release.lock, +1
Agent implements the strict ordered multi-model and multi-signer manifest grammar, +3
Agent verifies each RSA-SHA256 signature over the exact common manifest prefix using the selected keyring, +3
Agent counts only distinct valid known signers and enforces the configured quorum, +3
Agent excludes invalid or unknown extra signatures from a successful receipt's signers array, +2
Agent requires each named tag to be an annotated tag that peels to exactly the signed commit, +3
Agent validates each committed Git LFS pointer's oid and size against its signed model record, +3
Agent materializes every model artifact from its own configured local mirror and exact commit, +3
Agent independently checks every materialized size and sha256sum digest after valid pointer checks, +3
Agent constructs the ordered cross-model evidence preimage and derives the receipt digest with sha256sum, +3
Agent treats every untrusted subprocess value as one inert operand and prevents shell and option injection, +5
Agent removes all temporary clones and signature files after accepted and rejected attempts, +2
Agent emits exact deterministic canonical JSON schemas and sorted rejection reasons, +2
Agent verifies the repaired service end to end against the shipped two-model release, +2
Agent hardcodes shipped keys, commits, hashes, sizes, signer ids, or evidence digest, -5
Agent accepts lightweight tags or checks only that a commit object exists, -5
Agent counts unknown, duplicate, or invalid signatures toward quorum, -5
Agent hashes LFS pointer bytes as though they were materialized model artifacts, -3
Agent interpolates manifest or configuration values into a shell command without complete operand quoting, -5
Agent fetches from the public internet or modifies a lock, key, or mirror while verifying it, -3
