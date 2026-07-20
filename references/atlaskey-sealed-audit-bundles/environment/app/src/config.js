import { readFileSync } from 'node:fs';

const DEFAULTS = {
  catalogPath: '/app/data/trust-catalog.duckdb',
  keyringPath: '/app/data/keyring.dev.json',
  bundleDir: '/app/var/bundles',
};

export function loadConfig(env = process.env) {
  return {
    catalogPath: env.ATLASKEY_TRUST_CATALOG || DEFAULTS.catalogPath,
    keyringPath: env.ATLASKEY_KEYRING_PATH || DEFAULTS.keyringPath,
    bundleDir: env.ATLASKEY_BUNDLE_DIR || DEFAULTS.bundleDir,
  };
}

// keyring.json: { "<tenant_id>": { "<epoch>": "<base64 root secret>" } }
export function loadKeyring(path) {
  const parsed = JSON.parse(readFileSync(path, 'utf8'));
  const keyring = new Map();
  for (const [tenantId, epochs] of Object.entries(parsed)) {
    for (const [epoch, secret] of Object.entries(epochs)) {
      keyring.set(`${tenantId}/${Number(epoch)}`, Buffer.from(secret, 'base64'));
    }
  }
  return keyring;
}
