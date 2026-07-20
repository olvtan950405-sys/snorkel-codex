-- Trust catalog schema and the development seed data.
-- The signing stations are onboarded here; nothing about a tenant is trusted unless it is
-- in this catalog. Production ships a different catalog file with the same schema.

CREATE TABLE tenants (
    tenant_id     VARCHAR PRIMARY KEY,
    display_name  VARCHAR NOT NULL,
    status        VARCHAR NOT NULL  -- 'active' or 'suspended'
);

CREATE TABLE key_epochs (
    tenant_id     VARCHAR NOT NULL,
    epoch         INTEGER NOT NULL,
    key_id        VARCHAR NOT NULL,
    salt_hex      VARCHAR NOT NULL,  -- HKDF salt for this epoch's seal keys
    valid_from    TIMESTAMP NOT NULL,
    valid_until   TIMESTAMP,         -- NULL means the epoch is still open
    PRIMARY KEY (tenant_id, epoch)
);

CREATE TABLE allowed_algorithms (
    tenant_id     VARCHAR NOT NULL,
    algorithm     VARCHAR NOT NULL,
    PRIMARY KEY (tenant_id, algorithm)
);

CREATE TABLE revoked_keys (
    key_id        VARCHAR PRIMARY KEY,
    revoked_at    TIMESTAMP NOT NULL,
    reason        VARCHAR NOT NULL
);

-- Every seal accepted by the audit service lands here. A nonce may only ever appear once.
CREATE TABLE seal_ledger (
    nonce_hex     VARCHAR PRIMARY KEY,
    tenant_id     VARCHAR NOT NULL,
    bundle_id     VARCHAR NOT NULL,
    key_id        VARCHAR NOT NULL,
    sealed_at     TIMESTAMP NOT NULL
);

INSERT INTO tenants VALUES
    ('atlas-north', 'Atlas North Signing', 'active'),
    ('orbit-south', 'Orbit South Signing', 'active'),
    ('cinder-west', 'Cinder West Signing', 'suspended');

INSERT INTO key_epochs VALUES
    ('atlas-north', 3, 'atlas-north-2025h2',
     '6c638c9b34653046709c9c5d2b37299d25de9a2400b1917ee552f0a50bff2569',
     TIMESTAMP '2025-07-01 00:00:00', TIMESTAMP '2026-03-01 00:00:00'),
    ('atlas-north', 4, 'atlas-north-2026h1',
     '339847ff10ddd14da3e926ba15291ab283d9bfe89ef1cd03f2f81922c5927bec',
     TIMESTAMP '2026-03-01 00:00:00', NULL),
    ('orbit-south', 2, 'orbit-south-2026h1',
     '961801b65a31475810543ad972391054369c05ae217f7f5dd4b71b6eb80112f3',
     TIMESTAMP '2026-01-15 00:00:00', NULL),
    ('cinder-west', 1, 'cinder-west-2025h1',
     '60af2624ef5fc7d8b5a370fe294ab8227eadbe8027147c8673a99e21132c649d',
     TIMESTAMP '2025-01-01 00:00:00', NULL);

INSERT INTO allowed_algorithms VALUES
    ('atlas-north', 'AES-256-GCM+HMAC-SHA256'),
    ('orbit-south', 'AES-256-GCM+HMAC-SHA256'),
    ('orbit-south', 'AES-128-GCM+HMAC-SHA256'),
    ('cinder-west', 'AES-256-GCM+HMAC-SHA256');

INSERT INTO revoked_keys VALUES
    ('atlas-north-2025h2', TIMESTAMP '2026-02-01 00:00:00', 'signing laptop stolen from the field office');

-- Seals already audited on the previous catalog. The 2026-05-19 bundle was signed off last
-- week and the station has since re-shipped it.
INSERT INTO seal_ledger VALUES
    ('f09d2d67057294affe96041e07ea4e50', 'atlas-north', 'akb-2026-05-19-atlas-north',
     'atlas-north-2026h1', TIMESTAMP '2026-05-19 09:00:00');
