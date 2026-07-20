#!/bin/bash
set -euo pipefail

# Reference solution for the AtlasKey sealed-bundle audit task.
#
# Five things had to happen:
#   1. /app/src/akb/tar.js walked to the next header at the end of the member payload instead
#      of at the next 512-byte block boundary, so every archive whose members are not an exact
#      multiple of 512 bytes fell apart on the second member.
#   2. /app/src/akb/seal-v2.js did not exist beyond a stub. The v2 footer, worked out from the
#      v1 reader (field meanings, MAC coverage, key derivation, AAD), the vendor changelog
#      (little-endian, self-describing 4-byte-aligned records, a replay nonce, a key id, a
#      trailing CRC-32 over the MAC as well) and the bytes of the shipped bundles:
#
#        magic "AKB2" | u16 version=2 | u16 flags=0 | u32 header_len   (all little-endian)
#        header_len bytes of records: u8 tag | u16 len | value | zero pad to a 4-byte boundary
#          0x01 tenant id (utf-8)     0x04 algorithm (utf-8)   0x07 gcm iv (12)
#          0x02 key id (utf-8)        0x05 sealed_at (i64 ms)  0x08 gcm tag (16)
#          0x03 key epoch (u32)       0x06 replay nonce (16)   0x09 ciphertext
#        32-byte HMAC-SHA256 over everything ahead of it, then u32 CRC-32 over all of that.
#
#      Which 16-byte record is the nonce and which is the GCM tag is not written down
#      anywhere: only one assignment lets the payload decrypt, so trial decryption settles it.
#   3. /app/src/catalog/trust-catalog.js answered from pasted-in dev constants. Every answer
#      now comes from the DuckDB catalog the service was started with, and accepted seals are
#      appended to seal_ledger there.
#   4. /app/src/events/inventory.js hashed the raw Parquet bytes. The event table is loaded
#      with nodejs-polars and reduced to the row count, the high-risk count, and the content
#      digest the seal actually commits to.
#   5. /app/src/verify.js only checked the MAC. It now runs the four stages of the contract in
#      /app/docs/audit-api.md and records accepted seals.

cd /app

cat > /app/src/akb/tar.js <<'JS_EOF'
// Minimal ustar reader. Sealed bundles are plain uncompressed tars written by the
// signing stations, so this is all the tar support the service needs.

const BLOCK = 512;

function field(header, offset, length) {
  const raw = header.subarray(offset, offset + length);
  const end = raw.indexOf(0);
  return raw.subarray(0, end === -1 ? raw.length : end).toString('ascii');
}

function octal(header, offset, length) {
  const text = field(header, offset, length).trim();
  if (text === '') return 0;
  const value = parseInt(text, 8);
  if (!Number.isFinite(value)) throw new Error('malformed tar numeric field');
  return value;
}

export function readTar(buf) {
  const members = new Map();
  let off = 0;

  while (off + BLOCK <= buf.length) {
    const header = buf.subarray(off, off + BLOCK);
    if (header.every((byte) => byte === 0)) break; // end-of-archive marker

    const name = field(header, 0, 100);
    if (name === '') throw new Error('tar member has no name');
    const size = octal(header, 124, 12);
    const typeflag = String.fromCharCode(header[156]);

    const dataStart = off + BLOCK;
    const dataEnd = dataStart + size;
    if (dataEnd > buf.length) throw new Error(`tar member ${name} is truncated`);

    if (typeflag === '0' || typeflag === '\0') {
      members.set(name, buf.subarray(dataStart, dataEnd));
    }

    // Member payloads are padded out to a whole number of 512-byte blocks.
    off = dataStart + Math.ceil(size / BLOCK) * BLOCK;
  }

  if (members.size === 0) throw new Error('archive contains no regular files');
  return members;
}
JS_EOF

cat > /app/src/akb/seal-v2.js <<'JS_EOF'
import { crc32 } from 'node:zlib';

// Reader for the current seal footer (magic "AKB2").
export const V2_MAGIC = Buffer.from('AKB2', 'ascii');

const FIXED_HEADER_BYTES = 12; // magic + version + flags + header_len
const MAC_BYTES = 32;
const CRC_BYTES = 4;
const ALIGN = 4;

const TAG_TENANT_ID = 0x01;
const TAG_KEY_ID = 0x02;
const TAG_KEY_EPOCH = 0x03;
const TAG_ALGORITHM = 0x04;
const TAG_SEALED_AT = 0x05;
const TAG_NONCE = 0x06;
const TAG_GCM_IV = 0x07;
const TAG_GCM_TAG = 0x08;
const TAG_CIPHERTEXT = 0x09;

function readRecords(region) {
  const records = new Map();
  let off = 0;

  while (off < region.length) {
    // A record header needs three bytes; anything shorter is alignment padding at the end.
    if (off + 3 > region.length) {
      if (region.subarray(off).every((byte) => byte === 0)) break;
      throw new Error('malformed field record');
    }
    const tag = region[off];
    if (tag === 0) {
      // Zero padding between records.
      off += 1;
      continue;
    }
    const len = region.readUInt16LE(off + 1);
    const start = off + 3;
    const end = start + len;
    if (end > region.length) throw new Error('field record runs past the header');
    if (records.has(tag)) throw new Error(`duplicate field record 0x${tag.toString(16)}`);
    records.set(tag, region.subarray(start, end));
    off = end + ((ALIGN - (end % ALIGN)) % ALIGN);
  }

  return records;
}

function required(records, tag, name, expectedLength) {
  const value = records.get(tag);
  if (!value) throw new Error(`seal is missing ${name}`);
  if (expectedLength !== undefined && value.length !== expectedLength) {
    throw new Error(`${name} has unexpected length ${value.length}`);
  }
  return value;
}

export function parseSealV2(seal) {
  if (seal.length < FIXED_HEADER_BYTES || !seal.subarray(0, 4).equals(V2_MAGIC)) {
    throw new Error('not a v2 seal');
  }

  const version = seal.readUInt16LE(4);
  if (version !== 2) throw new Error(`unsupported seal version ${version}`);
  const flags = seal.readUInt16LE(6);
  if (flags !== 0) throw new Error(`reserved flag bits are set: ${flags}`);

  const headerLen = seal.readUInt32LE(8);
  const macOffset = FIXED_HEADER_BYTES + headerLen;
  const crcOffset = macOffset + MAC_BYTES;
  if (seal.length !== crcOffset + CRC_BYTES) throw new Error('seal length disagrees with header length');

  const records = readRecords(seal.subarray(FIXED_HEADER_BYTES, macOffset));

  const parsed = {
    formatVersion: 2,
    tenantId: required(records, TAG_TENANT_ID, 'tenant id').toString('utf8'),
    keyId: required(records, TAG_KEY_ID, 'key id').toString('utf8'),
    keyEpoch: required(records, TAG_KEY_EPOCH, 'key epoch', 4).readUInt32LE(0),
    algorithm: required(records, TAG_ALGORITHM, 'algorithm').toString('utf8'),
    sealedAtMs: Number(required(records, TAG_SEALED_AT, 'sealed_at', 8).readBigInt64LE(0)),
    nonce: Buffer.from(required(records, TAG_NONCE, 'replay nonce', 16)),
    gcmIv: Buffer.from(required(records, TAG_GCM_IV, 'gcm iv', 12)),
    gcmTag: Buffer.from(required(records, TAG_GCM_TAG, 'gcm tag', 16)),
    ciphertext: Buffer.from(required(records, TAG_CIPHERTEXT, 'ciphertext')),
    mac: Buffer.from(seal.subarray(macOffset, crcOffset)),
    macCovered: seal.subarray(0, macOffset),
  };

  // The trailer CRC covers the whole footer up to and including the MAC.
  const expectedCrc = crc32(seal.subarray(0, crcOffset));
  parsed.crcOk = expectedCrc === seal.readUInt32LE(crcOffset);

  if (!Number.isSafeInteger(parsed.sealedAtMs)) throw new Error('sealed_at is out of range');
  if (parsed.tenantId === '') throw new Error('tenant id is empty');
  if (parsed.keyId === '') throw new Error('key id is empty');

  return parsed;
}
JS_EOF

cat > /app/src/catalog/trust-catalog.js <<'JS_EOF'
import { DuckDBInstance } from '@duckdb/node-api';

function rows(reader) {
  return reader.getRowObjectsJS();
}

function toNumber(value) {
  return value === null || value === undefined ? null : Number(value);
}

export class TrustCatalog {
  constructor(instance, connection) {
    this.instance = instance;
    this.connection = connection;
  }

  static async open(path) {
    const instance = await DuckDBInstance.create(path);
    const connection = await instance.connect();
    return new TrustCatalog(instance, connection);
  }

  async tenant(tenantId) {
    const reader = await this.connection.runAndReadAll(
      'SELECT tenant_id, status FROM tenants WHERE tenant_id = $1',
      [tenantId],
    );
    return rows(reader)[0] ?? null;
  }

  async keyEpoch(tenantId, epoch) {
    const reader = await this.connection.runAndReadAll(
      `SELECT key_id, salt_hex,
              epoch_ms(valid_from) AS valid_from_ms,
              epoch_ms(valid_until) AS valid_until_ms
       FROM key_epochs
       WHERE tenant_id = $1 AND epoch = $2`,
      [tenantId, epoch],
    );
    const row = rows(reader)[0];
    if (!row) return null;
    return {
      keyId: row.key_id,
      saltHex: row.salt_hex,
      validFromMs: toNumber(row.valid_from_ms),
      validUntilMs: toNumber(row.valid_until_ms),
    };
  }

  async allowedAlgorithms(tenantId) {
    const reader = await this.connection.runAndReadAll(
      'SELECT algorithm FROM allowed_algorithms WHERE tenant_id = $1',
      [tenantId],
    );
    return rows(reader).map((row) => row.algorithm);
  }

  async revocation(keyId) {
    const reader = await this.connection.runAndReadAll(
      'SELECT epoch_ms(revoked_at) AS revoked_at_ms FROM revoked_keys WHERE key_id = $1',
      [keyId],
    );
    const row = rows(reader)[0];
    return row ? { revokedAtMs: toNumber(row.revoked_at_ms) } : null;
  }

  async isSealRecorded(nonceHex) {
    const reader = await this.connection.runAndReadAll(
      'SELECT 1 AS hit FROM seal_ledger WHERE nonce_hex = $1',
      [nonceHex],
    );
    return rows(reader).length > 0;
  }

  async recordSeal({ nonceHex, tenantId, bundleId, keyId, sealedAtMs }) {
    await this.connection.run(
      `INSERT INTO seal_ledger (nonce_hex, tenant_id, bundle_id, key_id, sealed_at)
       VALUES ($1, $2, $3, $4, make_timestamp(CAST($5 AS BIGINT)))`,
      [nonceHex, tenantId, bundleId, keyId, BigInt(sealedAtMs) * 1000n],
    );
  }

  async close() {
    this.connection.closeSync();
    this.instance.closeSync();
  }
}
JS_EOF

cat > /app/src/events/inventory.js <<'JS_EOF'
import pl from 'nodejs-polars';
import { canonicalJson, sha256Hex } from '../canonical.js';

const HIGH_RISK = ['high', 'critical'];

// The event table is a Parquet member inside the bundle; it is loaded with Polars and
// reduced to the three facts the seal commits to.
export function summarizeEvents(parquetBytes) {
  const frame = pl.readParquet(Buffer.from(parquetBytes)).sort('event_id');
  const records = frame.toRecords();

  const eventCount = frame.height;
  const highRiskEvents = frame.filter(pl.col('risk').isIn(HIGH_RISK)).height;

  const preimage = records.map((row) => `${canonicalJson(row)}\n`).join('');
  const contentDigest = sha256Hex(Buffer.from(preimage, 'utf8'));

  return { eventCount, highRiskEvents, contentDigest };
}
JS_EOF

cat > /app/src/verify.js <<'JS_EOF'
import { canonicalJson, sha256Hex } from './canonical.js';
import { readTar } from './akb/tar.js';
import { parseSealV2 } from './akb/seal-v2.js';
import { deriveSealKeys, sealAad } from './crypto/keys.js';
import { macMatches, openSealedPayload, suiteFor } from './crypto/seal.js';
import { summarizeEvents } from './events/inventory.js';

const MANIFEST_MEMBER = 'manifest.json';
const EVENTS_MEMBER = 'events.parquet';
const SEAL_MEMBER = 'seal.bin';

function finish(evidence, reasons) {
  const record = {
    ...evidence,
    reasons: [...new Set(reasons)].sort(),
    status: reasons.length === 0 ? 'accepted' : 'rejected',
  };
  return { ...record, evidence_digest: sha256Hex(Buffer.from(`${canonicalJson(record)}\n`, 'utf8')) };
}

export async function verifyBundle({ bundleId, archive, catalog, keyring }) {
  const evidence = {
    bundle_id: bundleId,
    content_digest: null,
    event_count: null,
    high_risk_events: null,
    key_epoch: null,
    manifest_digest: null,
    nonce: null,
    sealed_at: null,
    tenant_id: null,
  };

  // Structure: the archive, its event table, and the shape of the seal footer.
  let members;
  try {
    members = readTar(archive);
  } catch {
    return finish(evidence, ['MALFORMED_ARCHIVE']);
  }

  const manifestBytes = members.get(MANIFEST_MEMBER);
  const eventBytes = members.get(EVENTS_MEMBER);
  const sealBytes = members.get(SEAL_MEMBER);
  if (!manifestBytes || !eventBytes || !sealBytes) return finish(evidence, ['MALFORMED_ARCHIVE']);

  let summary;
  try {
    summary = summarizeEvents(eventBytes);
  } catch {
    return finish(evidence, ['MALFORMED_ARCHIVE']);
  }
  evidence.event_count = summary.eventCount;
  evidence.high_risk_events = summary.highRiskEvents;
  evidence.content_digest = summary.contentDigest;
  evidence.manifest_digest = sha256Hex(manifestBytes);

  let seal;
  try {
    seal = parseSealV2(sealBytes);
  } catch {
    return finish(evidence, ['MALFORMED_SEAL']);
  }
  evidence.tenant_id = seal.tenantId;
  evidence.key_epoch = seal.keyEpoch;
  evidence.sealed_at = new Date(seal.sealedAtMs).toISOString();
  evidence.nonce = seal.nonce.toString('hex');

  if (!seal.crcOk) return finish(evidence, ['SEAL_CRC_MISMATCH']);

  // Identity: who claims to have sealed this, and can we get at their key material?
  const tenant = await catalog.tenant(seal.tenantId);
  if (!tenant) return finish(evidence, ['UNKNOWN_TENANT']);

  const identityReasons = [];
  if (tenant.status !== 'active') identityReasons.push('TENANT_SUSPENDED');

  const suite = suiteFor(seal.algorithm);
  if (!suite) identityReasons.push('UNSUPPORTED_ALGORITHM');

  const epochRow = await catalog.keyEpoch(seal.tenantId, seal.keyEpoch);
  const rootSecret = keyring.get(`${seal.tenantId}/${seal.keyEpoch}`);
  if (!epochRow || !rootSecret) identityReasons.push('UNKNOWN_KEY_EPOCH');

  if (identityReasons.length > 0) return finish(evidence, identityReasons);

  // Cryptography: the seal must authenticate under the epoch's derived keys.
  const { macKey, encKey } = deriveSealKeys(rootSecret, epochRow.saltHex, suite.encKeyBytes);

  const cryptoReasons = [];
  if (!macMatches(macKey, seal.macCovered, seal.mac)) cryptoReasons.push('SEAL_HMAC_INVALID');

  const payload = openSealedPayload({
    suite,
    encKey,
    iv: seal.gcmIv,
    ciphertext: seal.ciphertext,
    tag: seal.gcmTag,
    aad: sealAad(seal.tenantId, seal.keyEpoch, seal.algorithm),
  });
  if (!payload || typeof payload !== 'object') cryptoReasons.push('SEAL_PAYLOAD_UNDECRYPTABLE');

  if (cryptoReasons.length > 0) return finish(evidence, cryptoReasons);

  // Trust: what the catalog says about this key, and what the sealed payload commits to.
  const reasons = [];
  if (seal.keyId !== epochRow.keyId) reasons.push('KEY_ID_MISMATCH');

  const revocation = await catalog.revocation(seal.keyId);
  if (revocation && seal.sealedAtMs >= revocation.revokedAtMs) reasons.push('KEY_REVOKED');

  const allowed = await catalog.allowedAlgorithms(seal.tenantId);
  if (!allowed.includes(seal.algorithm)) reasons.push('ALGORITHM_NOT_ALLOWED');

  if (epochRow.validFromMs !== null && seal.sealedAtMs < epochRow.validFromMs) {
    reasons.push('KEY_EPOCH_NOT_YET_VALID');
  }
  if (epochRow.validUntilMs !== null && seal.sealedAtMs >= epochRow.validUntilMs) {
    reasons.push('KEY_EPOCH_EXPIRED');
  }

  if (payload.manifest_digest !== evidence.manifest_digest) reasons.push('MANIFEST_DIGEST_MISMATCH');
  if (payload.event_count !== evidence.event_count) reasons.push('EVENT_COUNT_MISMATCH');
  if (payload.content_digest !== evidence.content_digest) reasons.push('EVENT_CONTENT_MISMATCH');

  if (await catalog.isSealRecorded(evidence.nonce)) reasons.push('SEAL_REPLAYED');

  if (reasons.length > 0) return finish(evidence, reasons);

  await catalog.recordSeal({
    nonceHex: evidence.nonce,
    tenantId: seal.tenantId,
    bundleId,
    keyId: seal.keyId,
    sealedAtMs: seal.sealedAtMs,
  });

  return finish(evidence, []);
}
JS_EOF


# Prove it against the shipped fixtures before handing back.
node - <<'CHECK_EOF'
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const service = spawn('node', ['/app/bin/atlaskey-audit.js', '--port', '8099'], {
  stdio: ['ignore', 'inherit', 'inherit'],
});

const expected = {
  'akb-2026-05-20-atlas-north': [],
  'akb-2026-05-21-orbit-south': [],
  'akb-2026-02-14-atlas-north': ['KEY_REVOKED'],
  'akb-2026-05-22-atlas-north': ['EVENT_CONTENT_MISMATCH'],
  'akb-2026-05-23-orbit-south': ['SEAL_CRC_MISMATCH'],
  'akb-2026-05-19-atlas-north': ['SEAL_REPLAYED'],
  'akb-2025-11-02-atlas-north': ['MALFORMED_SEAL'],
};

let failures = 0;
try {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const health = await fetch('http://127.0.0.1:8099/healthz');
      if (health.ok) break;
    } catch {
      await sleep(200);
    }
  }

  for (const [bundleId, reasons] of Object.entries(expected)) {
    const response = await fetch(`http://127.0.0.1:8099/audit-bundles/${bundleId}/verify`, {
      method: 'POST',
    });
    const verdict = await response.json();
    const ok = JSON.stringify(verdict.reasons) === JSON.stringify(reasons);
    if (!ok) failures += 1;
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${bundleId} -> ${verdict.status} ${JSON.stringify(verdict.reasons)}`);
  }
} finally {
  service.kill('SIGTERM');
}

if (failures > 0) {
  console.error(`${failures} fixture(s) did not verify as expected`);
  process.exit(1);
}
CHECK_EOF

# The smoke check accepted two bundles, which appended them to the development ledger.
# Put the dev catalog back the way the image ships it.
node /app/tools/seed-catalog.mjs /app/data/trust-catalog.sql /app/data/trust-catalog.duckdb

echo "solution applied"
