# GlacierVault bundle format, revision 3

A bundle directory contains `manifest.cbor`, `signatures.json`, and every segment named by the
manifest. Paths in a manifest are plain filenames: they must be non-empty UTF-8, must not contain
`/`, `\\`, NUL, or equal `.` or `..`, and must be unique.

The manifest is a canonical CBOR map with exactly these entries:

| key | value |
|---|---|
| `bundle_id` | non-empty text string |
| `tenant` | non-empty text string |
| `created_at` | non-negative integer, Unix milliseconds |
| `nonce` | 16-byte byte string |
| `segments` | non-empty array of segment maps |
| `merkle_root` | 32-byte byte string |

Each segment map has exactly `name` (a valid filename), `size` (a non-negative integer), and
`sha256` (32-byte byte string). Segment order is significant. Only definite-length maps, arrays,
text strings, and byte strings are permitted. Integers and lengths use their shortest CBOR
encoding. Map keys are ordered by their encoded-key length and then lexicographically by their
encoded bytes. No tags, floats, indefinite values, duplicate keys, or trailing bytes are allowed.
Thus the accepted file is byte-for-byte its own canonical re-encoding; merely decoding to the same
data model is insufficient.

Each leaf is `SHA-256(0x00 || segment_digest)`. Each internal node is
`SHA-256(0x01 || left || right)`. At an odd-width level, duplicate the last node before hashing.
The sole leaf is itself the root. Segment files must be opened beneath the bundle directory and
streamed; their actual byte count and digest must match the manifest.

`signatures.json` is a JSON array of objects with exactly `key_id` and `signature`. Both are
strings; `signature` is strict standard padded base64 decoding to exactly 64 bytes. A key may appear
only once. Each signature covers the exact bytes of `manifest.cbor` using Ed25519.
