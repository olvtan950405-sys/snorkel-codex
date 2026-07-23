# Task Explanation — Repair a Lua Git-LFS Model Lock Verification Gate

## Difficulty Explanation

This task combines four trust boundaries that each look deceptively simple in isolation. The agent must reconstruct a strict signed lock format from a conflicted implementation, authenticate the exact byte prefix, distinguish Git object existence from reachability by a published ref, and understand that the committed artifact is an LFS pointer rather than the artifact bytes. It must then materialize the exact commit and independently verify both the pointer commitments and fetched bytes. The entire chain is implemented in Lua using command-line tools, so correct supply-chain logic can still fail through shell or option injection. Partial repairs tend to accept an object merely because `cat-file` finds it, hash the pointer instead of the LFS object, verify a reserialized lock, or concatenate attacker-controlled operands into shell commands.

## Solution Explanation

The oracle replaces the conflicted module with a strict parser and a small subprocess boundary that quotes every operand. It verifies the signed prefix through `openssl`, uses Git plumbing to require a commit reachable from a head or tag, clones into a fresh temporary directory, reads each pointer from the commit itself, pulls LFS content for the detached locked revision, and checks materialized bytes with `wc` and `sha256sum`. Rejection reasons are deduplicated and sorted, output is deterministic compact JSON, and all temporary state is removed. The shipped conflicted lock is replaced by the pre-generated valid signed lock while its private signing key remains absent from the final image.

## Verification Explanation

The pytest verifier is black-box and generates a fresh RSA keypair, repository, bare remote, LFS object, commit, and signed lock for each behavioral group. It checks exact successful output, every conflict marker, malformed and ambiguous grammar, signature mutation, unknown commits, a real but deliberately dangling commit object, absent artifacts, pointer/lock disagreement, and configuration paths containing shell metacharacters. This prevents fixture hard-coding, distinguishes object existence from publication by a ref, and proves configuration values are treated as inert operands without prescribing a Lua subprocess API or source layout. An end-to-end default-fixture test confirms the oracle repaired the initial conflicts and that verification leaves both the lock and remote unchanged.
