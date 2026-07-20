# AtlasKey Sealer — release notes

## 2.0.0 (2026-05-18)

Seal format version 2. Stations upgraded in the 2026-05 fleet window; every bundle produced
after that window carries a v2 footer. Bundles already in the vault keep their v1 footers.

* The footer magic is now `AKB2` and the version field reads `2`.
* **Every integer in the footer is little-endian now.** v1 was big-endian; the byte order was
  a long-standing complaint from the station firmware team and it is finally gone.
* The footer body is no longer a fixed field order. It is a sequence of self-describing
  records — a one-byte tag, a two-byte length, then the value — and each record starts on a
  four-byte boundary, with zero bytes as padding. Readers must skip records whose tag they do
  not know: we intend to add more.
* The fixed part of the footer is the magic, the version, the reserved flags (still zero) and
  the total size of the record section that follows it.
* Two new fields: a per-seal replay nonce (the audit side asked for this after the re-flashed
  station incident) and the key id the station believes it is using. The ciphertext is now
  carried as a record like everything else, so its old explicit length field is gone.
* The MAC still authenticates every footer byte ahead of it, and it is still HMAC-SHA256 over
  the derived MAC key.
* New: the footer ends with a CRC-32 (IEEE, the zlib/gzip polynomial) over everything ahead of
  it, the MAC included. This is a transport check, not a security control — SD cards coming
  back from the field were arriving with flipped bytes and we would rather say so than fail a
  MAC and page someone.

Unchanged: the container layout, the manifest, the event table, both digest definitions, the
sealed payload, the algorithm suites, HKDF derivation and the GCM associated data. If you have
a working v1 verifier, the crypto half of it still applies as written.

Note for integrators: the format specification has not been updated yet (it still documents v1
only). Ticket ATK-2291 tracks it. Sorry.

## 1.4.2 (2026-01-09)

* Stations now refuse to seal an event table with zero rows.

## 1.4.0 (2025-11-20)

* Parquet writer upgraded; `amount_cents` is written as INT32 rather than INT64.
