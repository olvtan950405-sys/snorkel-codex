# Task Explanation — Repair an offline OCI provenance admission gate

*Category: Security. Reviewer-facing; the agent sees the instruction and `/app/docs/admission-contract.md`.*

## Difficulty explanation

`forgegate` is the final trust boundary for a disconnected container mirror. It walks a content-addressed OCI index, authenticates each selected platform's complete manifest graph, verifies builder-scoped Ed25519 provenance, enforces source and build policy, and consumes only precisely scoped vulnerability waivers. The shipped migration placeholder emits plausible admission objects from untrusted index annotations. A correct repair must keep descriptor bytes, provenance subjects, signer eligibility, builder identity, temporal boundaries, wildcard rules and waiver scope separate; a locally reasonable shortcut in any one of those areas can admit the wrong artifact.

## Solution explanation

The reference implementation validates the top-level schemas and all requested platform identities, resolves every descriptor through its digest and size, and refuses symlinks or malformed graphs before considering evidence. It strictly validates each provenance envelope, signs canonical payload bytes, counts distinct eligible Ed25519 keys against total and per-role requirements, then applies exact builder identity, literal source prefixes, the contract's glob semantics, commit/build-time rules and material trust. High and critical findings require waivers matching all identity, artifact, platform, source, commit and half-open time fields. It replaces the output tree and serializes platform verdicts and their aggregate evidence digest canonically.

## Verification explanation

The verifier builds fresh multi-platform OCI layouts, Ed25519 keyrings, provenance envelopes and policies outside `/app`, and computes expectations independently. It mutates graph bytes, descriptor sizes, subjects, duplicate signatures, key time boundaries, builder/source/ref fields, commit syntax, build intervals, material trust, findings and individual waiver dimensions. It also checks that direct executable invocation works, that mixed platform outcomes remain independent under a rejected aggregate image, that `ref_glob` treats regex metacharacters literally, that structurally valid provenance with semantic commit or build-time violations does not collapse into malformed evidence, that individually valid signers remain visible when quorum fails, and that a globally invalid layout writes only the aggregate report. Because manifests, keys, signatures, commits and waiver cases are generated per test, fixture-specific verdicts cannot pass.
