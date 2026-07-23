# Task Explanation — Repair a Quorum-Signed Lua Model Release Attestor

## Difficulty Explanation

This task tests a different trust model from a single-lock verifier: one exact manifest prefix covers multiple independently mirrored models and must receive a configurable quorum of maintainer signatures. Even after signature verification, the agent must distinguish an annotated Git tag object from a lightweight tag, peel it to the exact signed commit, inspect the committed LFS pointer before smudging, and validate the fetched bytes afterward. Finally it must build an ordered cross-model evidence preimage and return a stable receipt. These stages compound: implementations that validate each item in isolation still fail if they count unknown signers, accept a lightweight tag, hash pointer bytes, use a branch tip instead of the locked commit, or let one hostile operand escape into the shell.

## Solution Explanation

The oracle implements a strict phase-aware parser for model and signer records, verifies every detached RSA signature over the byte-exact common prefix, and counts only sorted unique key ids with present public keys. For each model it checks the remote tag object's type and peeled commit, clones into isolated temporary state, reads and validates the committed pointer, materializes LFS content, and independently checks size and SHA-256. Successful model records become a deterministic evidence stream whose digest anchors the canonical receipt. A single quoting boundary is used for all tool operands, while grammar restrictions, option terminators, cleanup, and read-only operation close the command-injection and mutation paths.

## Verification Explanation

The black-box verifier generates three fresh RSA keypairs and two fresh annotated-tag Git LFS mirrors rather than relying on shipped values. It independently computes the evidence receipt and checks exact bytes, including the integer model count and the exact set of valid signers. Focused cases cover insufficient quorum, an invalid extra signature alongside a valid quorum, signed-field tampering, lightweight tags, an annotated tag moved to a different commit, pointer/lock disagreement, each conflict marker, malformed ordering and paths, and a valid mirror-root path containing shell metacharacters. These are behavior checks rather than prescriptions about Lua subprocess APIs or source layout. The final default-fixture assertion confirms that the conflicted initial release was repaired while hashing the source lock before and after the endpoint call to prove read-only behavior.
