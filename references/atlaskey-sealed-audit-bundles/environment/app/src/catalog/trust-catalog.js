// Trust catalog access.
//
// The catalog is a DuckDB database (data/trust-catalog.sql is the schema and the development
// seed). None of that is wired up yet: the values below were pasted in from the dev catalog
// to get the endpoint returning something during the format migration, and the seal ledger
// only lives in memory, so it is gone the moment the service restarts.
//
// TODO: every answer in here has to come out of the catalog the service was started with.

const DEV_TENANTS = {
  'atlas-north': { tenant_id: 'atlas-north', status: 'active' },
  'orbit-south': { tenant_id: 'orbit-south', status: 'active' },
};

const DEV_EPOCH = {
  keyId: 'atlas-north-2026h1',
  saltHex: '339847ff10ddd14da3e926ba15291ab283d9bfe89ef1cd03f2f81922c5927bec',
  validFromMs: Date.UTC(2026, 2, 1),
  validUntilMs: null,
};

export class TrustCatalog {
  constructor(path) {
    this.path = path;
    this.seen = new Set();
  }

  static async open(path) {
    return new TrustCatalog(path);
  }

  async tenant(tenantId) {
    return DEV_TENANTS[tenantId] ?? null;
  }

  async keyEpoch(_tenantId, _epoch) {
    return DEV_EPOCH;
  }

  async allowedAlgorithms(_tenantId) {
    return ['AES-256-GCM+HMAC-SHA256'];
  }

  async revocation(_keyId) {
    return null;
  }

  async isSealRecorded(nonceHex) {
    return this.seen.has(nonceHex);
  }

  async recordSeal({ nonceHex }) {
    this.seen.add(nonceHex);
  }

  async close() {}
}
