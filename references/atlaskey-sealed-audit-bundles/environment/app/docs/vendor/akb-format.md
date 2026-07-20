# AtlasKey Bundle (.akb) format — specification v1.3

Status: current for **seal format version 1**. The v2 seal shipped with Sealer 2.0 is **not**
described here yet; see `CHANGELOG.md` in this directory for what the vendor says changed.

## 1. Container

An `.akb` file is an uncompressed POSIX tar (ustar). Three regular members, no directories:

| Member | Contents |
| --- | --- |
| `manifest.json` | UTF-8 JSON, station-written |
| `events.parquet` | Parquet event table |
| `seal.bin` | Binary seal footer |

Member order is not significant. Readers must not assume it.

## 2. manifest.json

```json
{
  "bundle_id": "akb-2026-05-04-atlas-north",
  "tenant_id": "atlas-north",
  "station_id": "sign-station-04",
  "produced_at": "2026-05-04T09:12:33.000Z",
  "event_file": "events.parquet",
  "event_count": 64
}
```

The manifest is convenience metadata for humans and for the vault index. It is **not**
authoritative: everything in it is restated inside the seal, and the seal wins.

## 3. events.parquet

One row per audit event. Columns, in any physical order:

| Column | Parquet type | Notes |
| --- | --- | --- |
| `event_id` | BYTE_ARRAY / UTF8 | unique within the bundle |
| `occurred_at` | BYTE_ARRAY / UTF8 | `YYYY-MM-DDTHH:mm:ss.sssZ` |
| `actor` | BYTE_ARRAY / UTF8 | |
| `action` | BYTE_ARRAY / UTF8 | |
| `resource` | BYTE_ARRAY / UTF8 | |
| `risk` | BYTE_ARRAY / UTF8 | `low`, `medium`, `high` or `critical` |
| `amount_cents` | INT32 | |

## 4. Digests

Canonical JSON, used everywhere in this spec, means: object keys sorted by code point,
compact separators (`,` and `:`), UTF-8, no insignificant whitespace.

* **`content_digest`** — take every row of the event table as a JSON object of the seven
  columns above, order the rows by `event_id` ascending, render each row as canonical JSON
  followed by a single `\n`, concatenate, and take the SHA-256 of the resulting UTF-8 bytes.
  Lowercase hex.
* **`manifest_digest`** — SHA-256 of the raw bytes of the `manifest.json` member, exactly as
  stored in the tar. Lowercase hex.

## 5. Sealed payload

The seal carries one AES-GCM ciphertext. Its plaintext is the canonical JSON of:

```json
{"content_digest": "<hex>", "event_count": 64, "manifest_digest": "<hex>"}
```

These three values are what the station commits to. A verifier recomputes all three from the
archive and compares.

## 6. Key material

Each tenant has a root secret per key epoch, held in the operator keyring; the trust catalog
holds the epoch's HKDF salt, its key id, and its validity window. Both seal keys come from
HKDF-SHA256 over the root secret:

| Key | Salt | Info | Length |
| --- | --- | --- | --- |
| MAC key | epoch salt | `atlaskey/seal/mac` | 32 bytes |
| Encryption key | epoch salt | `atlaskey/seal/enc` | suite key length |

The GCM associated data is the ASCII string `<tenant_id>|<key_epoch>|<algorithm>`, so a seal
cannot be lifted from one tenant, epoch or suite to another.

Suites emitted by the stations:

| Algorithm | Cipher | Encryption key |
| --- | --- | --- |
| `AES-256-GCM+HMAC-SHA256` | AES-256-GCM | 32 bytes |
| `AES-128-GCM+HMAC-SHA256` | AES-128-GCM | 16 bytes |

## 7. Seal footer, format version 1

All integers big-endian. Strings are UTF-8 with a single-byte length prefix. Fields appear in
exactly this order, with no padding:

| Field | Size | Notes |
| --- | --- | --- |
| magic | 4 | `AKB1` |
| version | 2 | `1` |
| flags | 2 | reserved, must be zero |
| tenant_id | 1 + n | length-prefixed |
| algorithm | 1 + n | length-prefixed |
| key_epoch | 4 | |
| sealed_at | 8 | signed milliseconds since the Unix epoch |
| gcm_iv | 12 | |
| gcm_tag | 16 | |
| ciphertext_len | 4 | |
| ciphertext | n | sealed payload, section 5 |
| mac | 32 | HMAC-SHA256 over every preceding byte of the footer |

There is no CRC and no replay nonce in v1: replay was tracked on `bundle_id`, which is why
duplicate submissions from a re-flashed station were such a headache in 2025.
