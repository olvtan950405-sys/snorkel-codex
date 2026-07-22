# Task Explanation — Audit rotating Gin JWTs and encrypted bbolt leases

_Category: Security. Reviewer-facing; the agent sees the concise instruction and `/app/docs/audit-contract.md`._

## Difficulty Explanation

This task joins several trust boundaries that are individually subtle and dangerous when combined. The audit cannot assume where the supplied server listens or stores state, so it must inspect a live process and still manage its lifecycle reliably. JWT verification spans a rotation: a token that merely decodes, uses a duplicated key ID, selects another algorithm, or is checked against only the final JWKS can yield a false result. The durable evidence is independently protected by AES-GCM inside bbolt and must be authenticated, decoded strictly, and reconciled bidirectionally with the verified tokens. Finally, the module supply-chain assertion needs two independent observations—an exact remote Git tag and Go's module origin metadata—without turning a remote, ref, or module string into an injection primitive.

## Solution Explanation

The oracle creates a private temporary directory, launches the configured binary, and uses `lsof` to discover its loopback listener and database descriptor. It replays each strict request sequentially and refreshes JWKS for every returned lease token. Headers, JWKs, signatures, issuer, audience, identities, lease IDs, and numeric times are validated before a token becomes evidence. After stopping and reaping the child, it opens the discovered database read-only with bbolt, authenticates and decrypts every lease with AES-256-GCM, and compares the sorted records field-for-field with the sorted token claims.

Module policy entries are validated and sorted, their exact tag refs are queried from Git with an argument vector and peeled when annotated, and `go mod download -json` must independently report the same origin commit and tag ref. Only a fully successful run atomically renames a canonical JSON report into place. Deferred cleanup covers temporary state and the child on every failure path.

## Verification Explanation

The behavioral verifier uses a fresh master key and request sequence whose lease order differs from report order, rotates between two issuances, and checks the resulting token and decrypted-record bindings rather than fixed timestamps. It confirms the child has been reaped, validates the canonical report shape, and pre-seeds the destination in failure cases to enforce atomicity. Unknown request fields, invalid keys, and a mutable module tag must fail without replacing evidence. The seeded command only writes an empty plausible report and therefore fails the runtime, JWT, database, and lifecycle checks; the oracle exercises the complete dynamic fixture.
