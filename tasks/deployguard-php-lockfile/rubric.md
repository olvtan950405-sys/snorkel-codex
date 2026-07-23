# Rubric 1
Agent reads the supplied webhook contract and SQLite schema before editing, +1
Agent authenticates the exact raw request bytes with HMAC-SHA256 and constant-time comparison, +3
Agent requires strict, single-valued key, timestamp, nonce, and signature headers and rejects malformed values, +2
Agent selects the signing secret only from SQLite by key ID and never from request JSON or other attacker-controlled metadata, +3
Agent enforces both the server clock-skew window and the selected key's half-open validity interval, +3
Agent parses JSON only after authentication and requires the exact documented top-level request schema and field types, +2
Agent validates Composer lock content, rejects duplicate package coordinates, and derives the documented deterministic fingerprint independent of package order, +4
Agent requires the submitted fingerprint to equal the derived fingerprint and the selected environment policy fingerprint, +3
Agent atomically claims an accepted nonce in SQLite so concurrent valid requests yield exactly one authorization, +4
Agent leaves the nonce table unchanged for all rejected requests, +2
Agent returns the documented status codes and exact JSON response shapes without leaking key material, +2
Agent preserves the public CLI and serves health and authorization requests end to end, +2
Agent verifies behavior with valid, rollover, tampering, stale timestamp, malformed lockfile, policy mismatch, replay, and concurrent requests, +2
Agent hardcodes fixture keys, fingerprints, release IDs, nonces, or expected bodies instead of implementing the contract, -5
Agent trusts a key or fingerprint supplied outside the selected database and policy rows, -5
Agent compares signatures with ordinary string equality or authenticates re-encoded JSON instead of the received bytes, -4
Agent checks for a nonce and records it in separate non-atomic operations, -4
Agent consumes a nonce before all authentication, payload, fingerprint, and policy checks succeed, -3
Agent edits the contract, seed database, or sample lockfile to force expected results, -3
