# Rubric 1
Agent runs the shipped export guard and inspects the worker, configuration, sample export, and repository state before editing, +1
Agent reads `/app/docs/contracts.md` before implementing the approval policy, +1
Agent replaces the mutable branch configuration with an exact semantic-version release tag and 40-character commit pin, +2
Agent resolves the configured tag independently from every policy mirror without falling back to a branch or another tag, +3
Agent requires at least two distinct mirrors and rejects a missing, unreachable, or divergent mirror with `POLICY_QUORUM_FAILED`, +4
Agent supports both annotated and lightweight release tags and derives the commit to which the selected tag peels, +2
Agent verifies that the resolved tag commit, configured `policyCommit`, and source-tree gitlink all identify the same commit, +4
Agent strictly validates the exact export schema, positive IDs, nonempty actor, lowercase SHA-256 OIDs, safe sizes, and nonempty chart collection, +3
Agent rejects duplicate chart IDs and thumbnail paths, absolute paths, traversal components, noncanonical separators, and unexpected fields, +3
Agent opens the DuckDB catalog selected by configuration or environment and queries the latest matching actor/dashboard decision, +3
Agent requires the latest audit decision to be `allow` and rejects missing, denied, malformed, or inaccessible audit state, +2
Agent loads `policy.json` from the pinned commit and validates its version, dashboard map, and sorted unique chart allowlists, +3
Agent rejects every exported chart not authorized for the selected dashboard by the pinned policy, +2
Agent reads each thumbnail as a committed canonical Git LFS v1 pointer before materializing content, +3
Agent requires every pointer OID and size to match the corresponding export record, +3
Agent fetches the LFS objects independently from every configured mirror and verifies each materialized byte size and SHA-256 digest, +4
Agent passes Git arguments as inert operands and prevents shell expansion and option injection from refs, paths, remotes, and configuration values, +4
Agent performs verification in isolated temporary state, removes temporary clones, and does not modify the export, database, source checkout, or mirrors, +3
Agent emits the exact compact approval schema or a lexicographically sorted, deduplicated rejection-reason array with one trailing newline, +3
Agent keeps the implementation in TypeScript and preserves `/app/bin/export-guard --export <path>` as the public command, +2
Agent verifies the repaired command end to end against the shipped release and inputs beyond the bundled fixture, +2
Agent hardcodes the shipped dashboard, actor, chart, commit, LFS OID, size, or expected output instead of implementing the general contract, -5
Agent accepts a branch, abbreviated revision, arbitrary tag name, current remote tip, or a one-mirror downgrade in place of quorum on the configured exact release, -5
Agent checks only the configured commit or tag while ignoring the source gitlink, -4
Agent trusts export-supplied thumbnail hashes without inspecting the committed pointer and materialized bytes, -5
Agent derives authorization from fixture constants or in-memory filtering instead of querying the configured DuckDB database, -4
Agent interpolates any untrusted value into a shell command or permits a leading-option operand to alter Git behavior, -5
Agent edits the supplied export, audit database, source checkout, policy mirrors, contract, or tests to force a passing result, -5
Agent emits nondeterministic ordering, tool diagnostics on stdout, or output that does not follow the documented one-line JSON contract, -3
