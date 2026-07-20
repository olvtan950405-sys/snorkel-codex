# Task Explanation — Repair a WireGuard peer-access reconciler

_Category: Security. Reviewer-facing; not copied into the agent environment._

## Difficulty explanation

`tunnelguard` is an enforcement generator for a zero-trust gateway. It joins a SQLite inventory with group policy, emergency grants, address pools, routes, and remotely served key events, then emits WireGuard, nftables, canonical JSON, and a human audit. The shipped program completes successfully and writes convincing artifacts, but uses textual CIDR tests, allow-first group logic, imprecise key-history matching, pre-normalization duplicate checks, and no real allocation or route-overlap model. Those defects compound: repairing key rotation still leaves unsafe routes, while repairing CIDRs still permits expired or denied access.

The expert challenge is faithful reconciliation across independently ordered evidence. It requires numeric IPv4/IPv6 reasoning, `/31` and `/127` boundary knowledge, mapped-address normalization, deny and emergency precedence, inclusive/exclusive time boundaries, compromise/rotation ordering, deterministic allocation, and canonical serialization. None is trivia and the public contract supplies every required rule.

## Solution explanation

Parse and validate policy and database evidence, normalize every address and network before comparison, then process enabled peers by byte-sorted ID. Resolve group allows minus all denies, add only active emergency grants, and replay applicable key events in stable temporal order. Validate or allocate each address numerically, normalize allowed routes, and retain routes only for earlier active peers so overlap precedence is deterministic. Apply the documented verdict order, generate enforcement only for active peers, and serialize the audit canonically with a digest over the peer array.

The oracle keeps a compiled Rust entry point and supplies a deterministic standard-library policy module under `/app/src`; it performs no network access except the required local key-event endpoint and derives every value from the selected inputs.

## Verification explanation

The pytest verifier rebuilds the Rust binary and exercises it only through its public command and environment variables. It uses temporary SQLite copies and an independent HTTP fixture server. Tests cover shipped verdicts, query cardinality, deny and emergency boundaries, deterministic allocation, mapped-address duplicates, numeric route overlaps, route authorization, future and inconsistent key events, canonical JSON and digest construction, enforcement exclusion, input-reordering invariance, and repeat-run byte identity. Mutations are generated outside `/app`, so hardcoded shipped answers cannot satisfy the suite.
