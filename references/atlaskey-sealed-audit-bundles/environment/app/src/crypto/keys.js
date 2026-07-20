import { hkdfSync } from 'node:crypto';

// Seal key derivation. Unchanged since the v1 format: HKDF-SHA256 over the tenant's
// epoch root secret, salted with the per-epoch salt held in the trust catalog.
const MAC_INFO = 'atlaskey/seal/mac';
const ENC_INFO = 'atlaskey/seal/enc';
const MAC_KEY_BYTES = 32;

export function deriveSealKeys(rootSecret, saltHex, encKeyBytes) {
  const salt = Buffer.from(saltHex, 'hex');
  const macKey = Buffer.from(hkdfSync('sha256', rootSecret, salt, Buffer.from(MAC_INFO, 'utf8'), MAC_KEY_BYTES));
  const encKey = Buffer.from(hkdfSync('sha256', rootSecret, salt, Buffer.from(ENC_INFO, 'utf8'), encKeyBytes));
  return { macKey, encKey };
}

// Associated data bound into the sealed payload. Also unchanged since v1.
export function sealAad(tenantId, keyEpoch, algorithm) {
  return Buffer.from(`${tenantId}|${keyEpoch}|${algorithm}`, 'utf8');
}
