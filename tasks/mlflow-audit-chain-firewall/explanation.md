# Task explanation — MLflow audit-chain firewall

## Difficulty

This task combines a domain-specific MLflow endpoint allowlist with security-sensitive recursive transformation and a byte-exact cryptographic ledger. Plausible fixes often redact only transport headers, accept route near misses, lose duplicate JSON keys, hash textual hex instead of digest bytes, include an accidental newline, or mutate the destination before discovering a late malformed record. Because each digest commits to every prior sanitized record, a small canonicalization mistake invalidates the remainder of the ledger.

## Oracle approach

The reference implementation token-decodes JSON to detect duplicates, validates the exact envelope and monotonic unique sequence numbers, then classifies routes before applying the body policy. It constructs fresh minimal rejection values and scrubbed forward values, canonical-encodes each base record without a newline, and advances SHA-256 from raw digest bytes. All records are staged in a sibling temporary file and renamed only after scanning, syncing, and closing succeeds.

## Verification

The tests rebuild submitted Go sources and exercise all route pairs, normalization and precedence, randomized credentials, nested tags, canonical presigned URLs, unsafe schemes/userinfo, exact independent hash-chain recomputation, tamper propagation, strict malformed-input handling, sequence and seed boundaries, destination preservation, defaults, deterministic output, and the shipped capture. Random values and independent digest calculation resist fixture-specific output substitution.
