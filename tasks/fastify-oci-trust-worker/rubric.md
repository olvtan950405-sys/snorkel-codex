Agent reads `/app/docs/trust-contract.md` and inspects the worker before editing, +1
Agent validates request, policy, corpus record, and OCI descriptor schemas strictly, +3
Agent resolves the exact remote tag without fetching or trusting a local mutable ref, +3
Agent requires an annotated tag and verifies its signature against an authorized release key, +4
Agent binds the tag target, corpus commit, artifact digest, and requested OCI digest together, +4
Agent validates OCI canonical bytes, SHA-256 digest, media type, image name, and platform, +3
Agent validates the required repository hooks as regular executable files with exact digests, +3
Agent rejects unsafe names, symlinks, duplicate records, and Git option injection, +3
Agent applies the specified deterministic rejection precedence, +2
Agent emits canonical summary and decision JSON with stable ordering and evidence digests, +3
Agent emits the exact escaped Graphviz graph and a stable `dot -Tplain` snapshot, +4
Agent keeps CLI and Fastify API behavior equivalent and offline, +2
Agent tests the public CLI against evidence beyond the shipped example, +2
Agent follows a local or fetched tag without independently resolving the remote advertisement, -5
Agent accepts a lightweight, unsigned, bad-key, or invalidly signed tag, -5
Agent trusts OCI annotations without digest binding to canonical artifact bytes, -5
Agent hardcodes shipped ids, hashes, graph text, or verdicts, -4
Agent modifies the corpus, remotes, keys, or policy to make the example pass, -4
Agent uses network services, current time, randomness, or input-order-dependent output, -3
