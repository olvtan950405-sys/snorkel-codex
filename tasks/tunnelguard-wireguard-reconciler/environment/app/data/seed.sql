CREATE TABLE pools(name TEXT PRIMARY KEY, cidr TEXT NOT NULL);
CREATE TABLE reservations(pool TEXT, address TEXT, reason TEXT);
CREATE TABLE peers(peer_id TEXT PRIMARY KEY, public_key TEXT, previous_key TEXT, pool TEXT, address TEXT, enabled INTEGER);
CREATE TABLE memberships(peer_id TEXT, group_name TEXT);
CREATE TABLE routes(peer_id TEXT, cidr TEXT);
CREATE TABLE emergency_access(peer_id TEXT, service TEXT, starts_at TEXT, expires_at TEXT);

INSERT INTO pools VALUES ('staff4','10.70.0.0/29'),('ops6','2001:db8:70::/125');
INSERT INTO reservations VALUES ('staff4','10.70.0.1','gateway'),('ops6','2001:db8:70::','gateway');
INSERT INTO peers VALUES
 ('alice','key-alice',NULL,'staff4','10.70.0.2',1),
 ('bob','key-bob-old','key-bob-new','staff4','10.70.0.3',1),
 ('carol','key-carol',NULL,'staff4','10.70.0.2',1),
 ('dave','key-dave',NULL,'ops6','2001:db8:70::2',1),
 ('disabled','key-disabled',NULL,'staff4','10.70.0.4',0);
INSERT INTO memberships VALUES
 ('alice','engineers'),('bob','engineers'),('carol','contractors'),('dave','operators');
INSERT INTO routes VALUES
 ('alice','10.80.10.0/25'),('bob','10.80.10.128/25'),('carol','10.80.30.0/24'),('dave','2001:db8:80::/120');
INSERT INTO emergency_access VALUES ('carol','prod-db','2026-06-01T00:00:00Z','2026-07-01T12:00:00Z');
