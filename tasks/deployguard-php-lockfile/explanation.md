# Task Explanation — PHP deploy webhook authorization

## Difficulty Explanation

This task combines four trust boundaries that are easy to implement plausibly but incorrectly. The HMAC must bind the timestamp, nonce, and byte-for-byte HTTP body; decoding and re-encoding JSON authenticates a different message. Key rollover requires selecting a secret from SQLite and checking the request instant against both the key interval and the server clock. Composer's lock format is order-insensitive for this policy, so dependencies need strict validation, de-duplication, sorting, and canonical hashing. Finally, replay protection is a database claim, not a cache check: validation followed by a separate insert permits two workers to authorize the same nonce.

## Solution Explanation

The oracle validates singleton headers and their exact lexical forms, loads the identified enabled key, checks time using integer arithmetic, decodes the supplied signature, and compares a fresh HMAC with `hash_equals`. Only then does it decode the body. It validates the exact payload keys and both Composer package arrays, creates sorted `name@version` coordinates, hashes their newline-joined UTF-8 representation, and compares the result with both the body assertion and the environment policy. The successful path uses `BEGIN IMMEDIATE` plus an insert into the nonce primary key; constraint or lock contention becomes a replay response, while every earlier rejection leaves the ledger untouched.

## Verification Explanation

The black-box verifier creates a fresh database with randomized secrets and policy fingerprints, launches the public PHP server, and signs newly generated bodies. It checks byte-level HMAC binding, rollover boundaries, clock skew, schema and lockfile failures, policy mismatch, replay, and a simultaneous duplicate claim. It also queries SQLite to ensure only accepted requests mutate the nonce ledger. The shipped implementation accepts decoded JSON using a client-provided secret, uses an unsafe comparison, omits complete fingerprinting, and records nonces non-atomically, so it cannot pass these generated cases.
