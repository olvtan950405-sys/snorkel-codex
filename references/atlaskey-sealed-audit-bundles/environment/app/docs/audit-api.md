# Audit service — API contract

The service is started with `node /app/bin/atlaskey-audit.js --port <n>` and reads three
paths from the environment. Defaults are the development ones; the staging and production
deployments override all three, so nothing about their contents may be baked into the code.

| Variable | Default |
| --- | --- |
| `ATLASKEY_TRUST_CATALOG` | `/app/data/trust-catalog.duckdb` |
| `ATLASKEY_KEYRING_PATH` | `/app/data/keyring.dev.json` |
| `ATLASKEY_BUNDLE_DIR` | `/app/var/bundles` |

If the trust catalog is not there, startup fails; a service that cannot answer trust questions
must not answer at all.

Every response body is canonical JSON — keys sorted by code point, compact, UTF-8 — with one
trailing newline, served as `application/json`.

## GET /healthz

`200` with `{"status":"ok"}`.

## POST /audit-bundles/:bundleId/verify

Verifies `<ATLASKEY_BUNDLE_DIR>/<bundleId>.akb`. No request body.

* A `bundleId` outside `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` is `400` `{"error":"invalid_bundle_id"}`.
* A bundle id with no file is `404` `{"error":"bundle_not_found"}`.
* Anything else is `200` and a verdict, including for a bundle that is complete rubbish.

### Verdict

```json
{
  "bundle_id": "akb-2026-05-04-atlas-north",
  "content_digest": "<hex>",
  "event_count": 64,
  "evidence_digest": "<hex>",
  "high_risk_events": 9,
  "key_epoch": 4,
  "manifest_digest": "<hex>",
  "nonce": "<hex>",
  "reasons": [],
  "sealed_at": "2026-05-04T09:12:33.000Z",
  "status": "accepted",
  "tenant_id": "atlas-north"
}
```

`status` is `accepted` when `reasons` is empty and `rejected` otherwise. `reasons` is sorted
and free of duplicates. `high_risk_events` counts rows whose `risk` is `high` or `critical`.

The four archive-derived fields (`content_digest`, `event_count`, `high_risk_events`,
`manifest_digest`) are reported whenever the archive itself could be read, whatever the seal
turns out to say. The four seal-derived fields (`key_epoch`, `nonce`, `sealed_at`,
`tenant_id`) are reported whenever the seal footer could be parsed. Fields that could not be
established are `null`.

`evidence_digest` is the SHA-256, lowercase hex, of the canonical JSON of the verdict with
`evidence_digest` itself left out, followed by one `\n` — the same bytes the response body
would have without that one field.

### Reasons

Checks run in four stages. A stage that produces any reason is the last stage that runs, and
every reason a stage produces is reported.

**Structure.** `MALFORMED_ARCHIVE` — not a readable tar, or a missing/unreadable member.
`MALFORMED_SEAL` — the seal footer does not parse, or is not seal format version 2 (v1 bundles
were migrated in May and are no longer accepted here). `SEAL_CRC_MISMATCH` — the footer's
transport CRC does not match.

**Identity.** `UNKNOWN_TENANT` — no such tenant in the catalog; this one is reported alone.
`TENANT_SUSPENDED` — the tenant's catalog status is not `active`. `UNKNOWN_KEY_EPOCH` — the
catalog has no epoch row for the sealed tenant and epoch, or the operator keyring holds no
root secret for it. `UNSUPPORTED_ALGORITHM` — an algorithm suite this service cannot open.

**Cryptography.** `SEAL_HMAC_INVALID` — the footer MAC does not verify under the derived MAC
key. `SEAL_PAYLOAD_UNDECRYPTABLE` — the sealed payload does not authenticate under the derived
encryption key.

**Trust.** `KEY_ID_MISMATCH` — the key id in the seal is not the key id the catalog has for
that epoch. `KEY_REVOKED` — the key is in the catalog's revocation list and the bundle was
sealed at or after the revocation instant; seals made before it stay trusted.
`ALGORITHM_NOT_ALLOWED` — the tenant's catalog allowlist does not carry the suite the station
used. `KEY_EPOCH_NOT_YET_VALID` / `KEY_EPOCH_EXPIRED` — the seal falls before the epoch's
`valid_from` or at/after its `valid_until` (an epoch with a null `valid_until` never expires).
`MANIFEST_DIGEST_MISMATCH`, `EVENT_COUNT_MISMATCH`, `EVENT_CONTENT_MISMATCH` — what the archive
actually contains is not what the sealed payload commits to. `SEAL_REPLAYED` — the seal's nonce
is already in the catalog's `seal_ledger`.

## Ledger

An accepted bundle appends its seal to `seal_ledger` (`nonce_hex`, `tenant_id`, `bundle_id`,
`key_id`, `sealed_at`) before the response goes out; verifying it a second time is therefore a
replay and is rejected. A rejected bundle leaves no trace: nothing about it is written back to
the catalog, no matter which stage rejected it.
