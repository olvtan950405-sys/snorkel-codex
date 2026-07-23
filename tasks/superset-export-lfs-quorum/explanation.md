# Task Explanation — Require Policy-Remote Quorum for Superset Exports

_Category: Security. Reviewer-facing; the agent sees the concise instruction and `/app/docs/contracts.md`._

## Difficulty Explanation

The export worker is the final authorization gate between an Apache Superset export and downstream publication. Its initial implementation appears functional, but it never establishes quorum on the trusted policy revision, never consults the audit catalog, and treats attacker-supplied thumbnail hashes as evidence. Repair therefore spans three independent trust boundaries: Git must resolve one exact release commit from every mirror and prove that the application source pins it as a submodule gitlink; DuckDB must supply the latest authorization decision; and Git LFS must bind each thumbnail to bytes fetched independently from every mirror.

The stages deliberately compound. A worker can resolve the correct tag yet remain vulnerable if it follows the checked-out submodule worktree rather than the `HEAD` gitlink. It can validate pointer metadata yet accidentally hash pointer text because LFS smudging was disabled. It can perform every cryptographic comparison correctly while still permitting shell or option injection through a remote path. Finally, all failure paths must collapse into stable, deduplicated reason codes without mutating any trusted input. Solving the task requires coordinating repository plumbing, strict untrusted-data validation, parameterized SQL, content-addressed storage, temporary-state cleanup, and byte-canonical CLI output.

## Solution Explanation

The reference repair first parses the export with an exact schema and validates IDs, paths, OIDs, sizes, and uniqueness before invoking external tools. It requires at least two distinct mirrors, queries the exact semantic-version tag from each one, peels annotated tags when necessary, and requires every result, `policyCommit`, and the mode-`160000` gitlink in the source repository's `HEAD` tree to agree. No checked-out branch or mutable worktree state participates in the decision.

After the supply-chain pin is established, the worker queries DuckDB for the newest decision, validates `policy.json`, and parses each canonical LFS pointer. Only after those bindings succeed does it use isolated clones to fetch LFS content from every mirror and independently hash and size each materialized file. Git is invoked with argument arrays and option boundaries, temporary state is cleaned up on every path, and the result is one compact deterministic JSON line.

## Verification Explanation

The verifier is black-box and drives only `/app/bin/export-guard`. Its primary fixture creates a fresh policy repository, annotated semantic-version tag, two bare local mirrors, source repository with a pinned gitlink, Git LFS thumbnail, DuckDB audit catalog, and matching Superset export. Dynamic commit IDs, paths, OIDs, sizes, and database files prevent a fixture-specific implementation from passing.

Focused cases replace the release tag with a mutable branch, mismatch the configured pin, append a newer audit denial, request a chart absent from policy, alter the exported OID or size, and inject path traversal. A remote whose filename contains shell metacharacters verifies that the value remains one inert operand and creates no side-effect file. The suite also hashes the export, configuration, and DuckDB database before and after approval to enforce read-only behavior, compares successful output byte-for-byte with canonical JSON, and finally checks that the shipped branch-following configuration was repaired and works end to end. The seeded worker fails the trust, authorization, LFS, and configuration checks; the oracle is designed to satisfy them without relying on bundled constants.
