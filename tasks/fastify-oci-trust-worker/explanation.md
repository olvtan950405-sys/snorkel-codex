# Design and oracle

This task models a supply-chain incident in which several individually plausible facts are not transitively trustworthy. The repair must establish one chain: an independently advertised remote annotated tag, a valid signature by a policy-authorized key, its peeled commit, the corpus record for that commit, the byte-exact OCI artifact digest, and the mandatory hooks in that same commit. Mutable refs, filenames, annotations, and the corpus verdict are descriptive only.

The oracle uses inert argument vectors for Git, validates every input before using it as a path or operand, verifies the annotated tag with a temporary isolated keyring, reads committed hook blobs without checking out the repository, and canonicalizes JSON recursively. It constructs Graphviz from validated identifiers using explicit escaping, then lets the pinned `dot` binary produce the plain snapshot. CLI and HTTP call the same verifier, so there is no second policy implementation to drift.

Tests build fresh signed and adversarial repositories and corpus snapshots. They cover mutable/lightweight tags, unauthorized and invalid signatures, commit/digest/platform mismatches, hook mode and content failures, malformed and duplicate corpus records, deterministic output replacement, graph escaping, and byte equality between CLI and API results.
