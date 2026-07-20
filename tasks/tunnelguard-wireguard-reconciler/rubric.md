# Rubric 1
Agent reads `/app/docs/access-policy-spec.md` before implementing the repair, +1
Agent inspects the SQLite schema and representative rows before editing source, +1
Agent runs the shipped tool against a local key-event service and inspects all four artifacts, +1
Agent parses IPv4 and IPv6 addresses and CIDRs numerically and normalizes masked network addresses, +3
Agent converts IPv4-mapped IPv6 addresses before comparison and serialization, +2
Agent implements usable-address semantics including IPv4 `/31` and `/32` boundaries, +2
Agent deterministically allocates the lowest usable unreserved address not assigned to another enabled peer, +3
Agent combines group policy so every deny overrides every allow regardless of membership order, +2
Agent applies emergency access with inclusive start and exclusive expiry and ignores invalid intervals, +2
Agent queries key evidence exactly once per enabled peer and fails closed on unavailable or malformed evidence, +3
Agent replays compromise and rotation events using the documented time and same-instant ordering, +3
Agent distinguishes revoked, staged rotation, and inconsistent key histories according to the contract, +3
Agent verifies each normalized route is contained by an effectively allowed service network, +2
Agent detects numeric route overlap and gives the byte-sorted earlier active peer precedence, +3
Agent applies the full verdict precedence without allowing lower-priority conflicts to mask evidence failures, +2
Agent emits only active peers in WireGuard and nftables configuration at the exact required paths, +2
Agent emits canonical audit JSON with all eight count keys and the peer-array SHA-256 digest, +3
Agent preserves the compiled Rust entry point and rebuilds `/app/bin/tunnelguard`, +2
Agent verifies the repair end to end using more than the shipped inventory, +3
Agent hardcodes shipped peer verdicts, addresses, routes, or digest values, -5
Agent compares addresses, CIDRs, or timestamps using raw textual prefix or lexical shortcuts, -3
Agent edits the shipped database, policy, or event fixtures to force expected outcomes, -3
Agent leaves the Rust project in a state that does not compile, -3
Agent introduces current time, randomness, row-order dependence, or other nondeterminism, -2
Agent contacts any network endpoint other than the selected key-event API, -2
