import { canonicalJson, sha256Hex } from './canonical.js';
import { readTar } from './akb/tar.js';
import { parseSealV2 } from './akb/seal-v2.js';
import { deriveSealKeys } from './crypto/keys.js';
import { macMatches, suiteFor } from './crypto/seal.js';
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

// Half of this survived the format migration. The structural pass is here and the MAC is
// checked, but the CRC, the sealed payload, everything the catalog is supposed to say about
// the key, and the replay ledger are all still missing. docs/audit-api.md is the contract.
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

  const summary = summarizeEvents(eventBytes);
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

  const tenant = await catalog.tenant(seal.tenantId);
  if (!tenant) return finish(evidence, ['UNKNOWN_TENANT']);

  const suite = suiteFor(seal.algorithm);
  const epochRow = await catalog.keyEpoch(seal.tenantId, seal.keyEpoch);
  const rootSecret = keyring.get(`${seal.tenantId}/${seal.keyEpoch}`);
  const { macKey } = deriveSealKeys(rootSecret, epochRow.saltHex, suite.encKeyBytes);

  if (!macMatches(macKey, seal.macCovered, seal.mac)) return finish(evidence, ['SEAL_HMAC_INVALID']);

  return finish(evidence, []);
}
