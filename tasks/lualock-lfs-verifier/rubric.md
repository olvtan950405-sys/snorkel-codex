Agent runs the conflicted lockguard service and inspects its failure before editing, +1
Agent reads /app/docs/lock-verification.md and inspects the model remote and LFS pointer, +1
Agent removes the rebase conflicts in both /app/verify_service.lua and /app/deps.lock, +1
Agent implements the complete strict lock grammar including canonical ordering, paths, hashes, sizes, and conflict detection, +3
Agent verifies the detached RSA-SHA256 signature over the exact signed prefix using the configured maintainer public key, +3
Agent establishes that the exact locked object is a commit reachable from a ref in the configured remote, +3
Agent rejects a commit that exists in the remote object database but is unreachable from every published head and tag, +3
Agent inspects the committed Git LFS pointer and validates its oid and size against the signed lock, +3
Agent materializes the locked revision's LFS objects in a fresh temporary checkout, +3
Agent independently verifies materialized artifact byte sizes and sha256sum digests after valid pointer checks, +3
Agent safely treats untrusted subprocess values as single operands and prevents shell and option injection, +5
Agent removes temporary worktrees and files after both successful and rejected verification, +2
Agent emits the documented deterministic status codes and canonical JSON response schemas, +2
Agent preserves the source lockfile and remote across verification attempts, +2
Agent verifies the repaired endpoint end to end against the shipped model fixture, +2
Agent hardcodes the shipped commit, artifact digest, size, model id, or accepted response, -5
Agent disables signature, remote reachability, LFS pointer, or materialized-content validation, -5
Agent interpolates lockfile or configuration values into a shell command without complete operand quoting, -5
Agent modifies the remote or lockfile during endpoint verification, -3
Agent fetches from the internet or replaces the configured local remote with a public network URL, -3
