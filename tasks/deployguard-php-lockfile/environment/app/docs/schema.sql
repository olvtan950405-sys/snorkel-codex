PRAGMA foreign_keys = ON;
CREATE TABLE signing_keys (
  key_id TEXT PRIMARY KEY,
  secret TEXT NOT NULL,
  not_before INTEGER NOT NULL,
  not_after INTEGER NOT NULL,
  enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
  CHECK (not_before < not_after)
);
CREATE TABLE deploy_policies (
  environment TEXT PRIMARY KEY,
  lock_fingerprint TEXT NOT NULL CHECK (length(lock_fingerprint) = 64)
);
CREATE TABLE accepted_nonces (
  key_id TEXT NOT NULL,
  nonce TEXT NOT NULL,
  release_id TEXT NOT NULL,
  accepted_at INTEGER NOT NULL,
  PRIMARY KEY (key_id, nonce),
  FOREIGN KEY (key_id) REFERENCES signing_keys(key_id)
);
