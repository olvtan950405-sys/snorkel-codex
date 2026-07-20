PRAGMA foreign_keys = ON;
CREATE TABLE tenants(tenant TEXT PRIMARY KEY, status TEXT NOT NULL);
CREATE TABLE keys(
  key_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, role TEXT NOT NULL,
  public_key BLOB NOT NULL, active_from INTEGER NOT NULL,
  active_until INTEGER, revoked_at INTEGER
);
CREATE TABLE quorum_policies(
  tenant TEXT NOT NULL, effective_from INTEGER NOT NULL,
  operator_required INTEGER NOT NULL, recovery_required INTEGER NOT NULL,
  total_required INTEGER NOT NULL, PRIMARY KEY(tenant,effective_from)
);
CREATE TABLE emergency_exceptions(
  exception_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, key_id TEXT NOT NULL,
  valid_from INTEGER NOT NULL, valid_until INTEGER NOT NULL, bundle_prefix TEXT NOT NULL
);
CREATE TABLE accepted_nonces(
  tenant TEXT NOT NULL, nonce BLOB NOT NULL, bundle_id TEXT NOT NULL,
  manifest_digest TEXT NOT NULL, created_at INTEGER NOT NULL,
  PRIMARY KEY(tenant,nonce)
);
