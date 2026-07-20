Agent reads /app/docs/admission-contract.md and inspects the shipped implementation before editing, +1
Agent validates oci-layout and index schemas before evaluating provenance, +2
Agent resolves every manifest, config, and layer through exact SHA-256 and byte-size descriptors, +3
Agent rejects symlinks, unsafe digest paths, duplicate platforms, and incomplete requested platform sets, +3
Agent binds config platform fields to the platform selected by the index, +2
Agent strictly validates provenance schemas, ordering, uniqueness, instants, and canonical payload representation, +3
Agent verifies Ed25519 signatures over canonical payload bytes using only builder-owned eligible keys, +3
Agent counts each distinct valid key once and enforces total and per-role signature minima together, +3
Agent binds each provenance subject to the selected manifest digest, +2
Agent enforces exact builder identity, literal source prefix, contract glob, commit, and build-time policy, +3
Agent validates all material digests and restricts every material URI to a trusted prefix, +2
Agent applies waivers only when every artifact, finding, builder, source, commit, platform, and time dimension matches, +3
Agent rejects unwaived critical or high findings while retaining all findings in evidence, +3
Agent replaces stale output and emits only the contract-defined per-platform and aggregate artifacts, +2
Agent emits canonical JSON, deterministic platform/signer/waiver ordering, and the correct evidence digest, +3
Agent exercises the public CLI against evidence beyond the shipped example before finishing, +2
Agent trusts index annotations as provenance or policy evidence, -5
Agent verifies a signature without binding its payload subject to the selected manifest, -5
Agent counts duplicate signatures or ineligible keys toward a threshold, -5
Agent broadens waiver matching by omitting any required scope dimension, -5
Agent edits /app/data inputs or hardcodes their digests, identities, verdicts, or waiver IDs, -3
Agent introduces network access, wall-clock time, randomness, or input-order dependence, -3
Agent leaves /app/bin/forgegate unable to run with Ruby, -3
