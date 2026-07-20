# Offline verifier contract

The command writes one verdict object with exactly `bundle_id`, `manifest_digest`, `nonce`,
`signers`, `status`, and `tenant`. JSON is recursively key-sorted, compact UTF-8, and ends in exactly
one newline. `signers` is the sorted list of distinct valid, eligible key IDs that contributed to an
accepted quorum; it is empty for every rejection. Descriptive fields are populated as soon as a
canonical manifest makes them trustworthy; before then they are null. The digest is lowercase
SHA-256 of the canonical manifest, and the nonce is lowercase hex.

Exactly one status is emitted, using this precedence:

1. `bundle_unreadable`: a required file is absent, unsafe, malformed, truncated, or violates its schema.
2. `manifest_noncanonical`: CBOR decodes to the manifest schema but is not its unique canonical encoding.
3. `segment_invalid`: a segment is absent, not a regular file, has the wrong size, or has the wrong digest.
4. `merkle_mismatch`: segment leaves do not produce the committed root.
5. `tenant_unknown`: no active tenant row exists for the manifest tenant.
6. `key_untrusted`: a listed key is missing, belongs to another tenant, has an unrecognized role, is outside its activation interval, or was revoked at or before `created_at`, unless a matching emergency exception applies.
7. `signature_invalid`: a signature entry is malformed or its Ed25519 verification fails.
8. `quorum_not_met`: the distinct valid eligible signatures do not meet every selected policy threshold.
9. `replayed`: the tenant and nonce already occur in `accepted_nonces`.
10. `accepted`: all checks pass and the nonce is newly recorded.

Catalog intervals are half-open: `active_from <= created_at < active_until`; a null end has no upper
bound. Revocation applies when `revoked_at <= created_at`. An exception applies only when tenant,
key, time interval, and `bundle_prefix` (a literal prefix of `bundle_id`) all match. It excuses key
activation/expiry/revocation only; it never changes tenant membership, role, signature validity, or
quorum counts.

Select the policy for the tenant with the greatest `effective_from <= created_at`. Counts are minima:
`operator_required`, `recovery_required`, and `total_required` must all be satisfied by distinct keys.
The acceptance insert must be transactional and race-safe. Store tenant, nonce, bundle ID, manifest
digest, and `created_at`; a rejected verification must leave the catalog unchanged.

The SQLite schema is the source of truth and is defined in `/app/docs/catalog-schema.sql`.
